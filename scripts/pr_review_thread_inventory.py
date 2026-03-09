from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GRAPHQL_QUERY = """
query UnresolvedReviewThreads($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      url
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          path
          line
          originalLine
          comments(first: 1) {
            nodes {
              body
              url
            }
          }
        }
      }
    }
  }
}
""".strip()


@dataclass(frozen=True)
class ThreadRecord:
    thread_url: str
    path: str
    line: int | None
    is_resolved: bool
    summary: str


def _coerce_line(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _summarize_comment(body: str, max_words: int = 24) -> str:
    compact = " ".join(body.split())
    if not compact:
        return "(no reviewer text available)"
    words = compact.split(" ")
    if len(words) <= max_words:
        return compact
    return " ".join(words[:max_words]) + "..."


def parse_review_threads(
    payload: dict[str, Any], unresolved_only: bool = True
) -> list[ThreadRecord]:
    repository = payload.get("data", {}).get("repository")
    if not repository:
        raise ValueError("Missing repository payload in GraphQL response")

    pull_request = repository.get("pullRequest")
    if not pull_request:
        raise ValueError("Missing pullRequest payload in GraphQL response")

    nodes = pull_request.get("reviewThreads", {}).get("nodes") or []
    records: list[ThreadRecord] = []

    for node in nodes:
        is_resolved = bool(node.get("isResolved"))
        if unresolved_only and is_resolved:
            continue

        comments = node.get("comments", {}).get("nodes") or []
        first_comment = comments[0] if comments else {}
        thread_url = str(first_comment.get("url") or "").strip()

        records.append(
            ThreadRecord(
                thread_url=thread_url,
                path=str(node.get("path") or "").strip(),
                line=_coerce_line(node.get("line")) or _coerce_line(node.get("originalLine")),
                is_resolved=is_resolved,
                summary=_summarize_comment(str(first_comment.get("body") or "")),
            )
        )

    return records


def render_markdown(records: list[ThreadRecord]) -> str:
    lines = [
        "| Thread URL | File | Line | Status | Summary |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        status = "resolved" if record.is_resolved else "unresolved"
        line_text = str(record.line) if record.line is not None else ""
        url = record.thread_url if record.thread_url else "(missing-url)"
        lines.append(f"| {url} | {record.path} | {line_text} | {status} | {record.summary} |")
    return "\n".join(lines)


def render_structured_list(records: list[ThreadRecord]) -> str:
    lines = [
        "# Unresolved Review Thread Inventory",
        "",
        f"Total threads: {len(records)}",
        "",
    ]

    for index, record in enumerate(records, start=1):
        line_text = str(record.line) if record.line is not None else "unknown"
        url = record.thread_url if record.thread_url else "(missing-url)"
        lines.append(f"{index}. Thread: {url}")
        lines.append(f"   - Location: `{record.path}:{line_text}`")
        lines.append(f"   - Summary: {record.summary}")
    return "\n".join(lines)


def fetch_graphql_payload(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    cmd = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={GRAPHQL_QUERY}",
        "-F",
        f"owner={owner}",
        "-F",
        f"repo={repo}",
        "-F",
        f"number={pr_number}",
    ]
    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def load_payload(input_json: Path | None, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    if input_json is not None:
        return json.loads(input_json.read_text(encoding="utf-8"))
    return fetch_graphql_payload(owner=owner, repo=repo, pr_number=pr_number)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a markdown inventory of review threads for a pull request."
    )
    parser.add_argument("--owner", default="stranske")
    parser.add_argument("--repo", default="Inv-Man-Intake")
    parser.add_argument("--pr-number", type=int, default=85)
    parser.add_argument(
        "--input-json",
        type=Path,
        help="Path to saved GraphQL response JSON; skips live GitHub API call when provided.",
    )
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="Include resolved review threads in output.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional markdown output file path. If omitted, writes to stdout.",
    )
    parser.add_argument(
        "--format",
        choices=("table", "structured-list"),
        default="table",
        help="Output format: markdown table or structured list.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    payload = load_payload(
        input_json=args.input_json,
        owner=args.owner,
        repo=args.repo,
        pr_number=args.pr_number,
    )
    records = parse_review_threads(payload, unresolved_only=not args.include_resolved)
    markdown = (
        render_markdown(records) if args.format == "table" else render_structured_list(records)
    )

    if args.output:
        args.output.write_text(markdown + "\n", encoding="utf-8")
    else:
        sys.stdout.write(markdown + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
