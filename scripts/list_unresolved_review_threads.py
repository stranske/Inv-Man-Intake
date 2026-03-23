#!/usr/bin/env python3
"""List unresolved inline review threads for a pull request."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

GRAPHQL_QUERY = """
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      number
      reviewThreads(first: 100) {
        nodes {
          isResolved
          comments(first: 20) {
            nodes {
              url
              body
              path
              line
              originalLine
              author {
                login
              }
            }
          }
        }
      }
    }
  }
}
""".strip()


@dataclass(frozen=True)
class UnresolvedThread:
    """Structured record for an unresolved review thread."""

    thread_url: str
    comment_url: str
    author: str
    comment_text: str
    path: str
    line: int | None


def _first_comment(thread_node: dict[str, Any]) -> dict[str, Any] | None:
    comments = (thread_node.get("comments", {}) or {}).get("nodes", [])
    if not isinstance(comments, list) or not comments:
        return None
    first = comments[0]
    return first if isinstance(first, dict) else None


def parse_unresolved_threads(payload: dict[str, Any]) -> list[UnresolvedThread]:
    """Extract unresolved threads from a GitHub GraphQL pull request response."""
    nodes = (
        payload.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes", [])
    )
    if not isinstance(nodes, list):
        return []

    results: list[UnresolvedThread] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("isResolved") is True:
            continue
        first_comment = _first_comment(node)
        if not first_comment:
            continue

        comment_url = str(first_comment.get("url", "")).strip()
        if not comment_url:
            continue
        thread_url = comment_url.split("#", 1)[0]
        path = str(first_comment.get("path", "")).strip()
        if not path:
            path = "(unknown-path)"

        author = (first_comment.get("author") or {}).get("login")
        if not isinstance(author, str) or not author:
            author = "unknown"

        line = first_comment.get("line")
        if line is None:
            line = first_comment.get("originalLine")
        if not isinstance(line, int):
            line = None

        comment_text = str(first_comment.get("body", "")).strip()
        results.append(
            UnresolvedThread(
                thread_url=thread_url,
                comment_url=comment_url,
                author=author,
                comment_text=comment_text,
                path=path,
                line=line,
            )
        )

    return results


def _load_from_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_from_gh(owner: str, repo: str, pr: int) -> dict[str, Any]:
    variables = {"owner": owner, "repo": repo, "pr": pr}
    cmd = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={GRAPHQL_QUERY}",
        "-f",
        f"variables={json.dumps(variables)}",
    ]
    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _as_markdown(pr: int, threads: list[UnresolvedThread]) -> str:
    lines = [f"# PR #{pr} Unresolved Inline Review Threads", ""]
    if not threads:
        lines.append("No unresolved inline review threads found.")
        return "\n".join(lines)

    lines.extend(
        [
            "| Thread URL | Comment URL | Author | Location | Quoted Comment Text |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in threads:
        line_text = str(item.line) if item.line is not None else "unknown"
        location = f"`{item.path}:{line_text}`"
        comment = item.comment_text.replace("\n", " ").replace("|", "\\|")
        lines.append(
            f"| {item.thread_url} | {item.comment_url} | {item.author} | {location} | {comment} |"
        )

    return "\n".join(lines)


def _as_checklist(pr: int, threads: list[UnresolvedThread]) -> str:
    lines = [f"# PR #{pr} Unresolved Inline Review Threads", ""]
    if not threads:
        lines.append("No unresolved inline review threads found.")
        return "\n".join(lines)

    lines.append("## Thread Documentation")
    lines.append("")
    for index, item in enumerate(threads, start=1):
        line_text = str(item.line) if item.line is not None else "unknown"
        location = f"`{item.path}:{line_text}`"
        quoted = item.comment_text.strip()
        if not quoted:
            quoted = "(no comment text)"
        quoted = quoted.replace("\r\n", "\n").replace("\r", "\n")
        quote_block = "\n".join(f"> {line}" if line else ">" for line in quoted.split("\n"))

        lines.append(f"{index}. Thread URL: {item.thread_url}")
        lines.append(f"Comment URL: {item.comment_url}")
        lines.append(f"Author: `{item.author}`")
        lines.append(f"Location: {location}")
        lines.append("Quoted comment text:")
        lines.append(quote_block)
        lines.append("")

    return "\n".join(lines).rstrip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="stranske")
    parser.add_argument("--repo", default="Inv-Man-Intake")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--input-json", type=Path, default=None)
    parser.add_argument(
        "--format",
        choices=("json", "markdown", "checklist"),
        default="markdown",
        help="Output format for unresolved thread details.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        payload = (
            _load_from_file(args.input_json)
            if args.input_json
            else _load_from_gh(
                owner=args.owner,
                repo=args.repo,
                pr=args.pr,
            )
        )
    except (json.JSONDecodeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"failed to load pull request review thread payload: {exc}", file=sys.stderr)
        return 1

    threads = parse_unresolved_threads(payload)
    if args.format == "json":
        print(json.dumps([asdict(item) for item in threads], indent=2))
    elif args.format == "checklist":
        print(_as_checklist(args.pr, threads))
    else:
        print(_as_markdown(args.pr, threads))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
