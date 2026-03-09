#!/usr/bin/env python3
"""List unresolved inline review threads for a GitHub pull request."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReviewThread:
    thread_id: str
    is_resolved: bool
    path: str | None
    line: int | None
    url: str | None


QUERY = """
query($owner: String!, $name: String!, $prNumber: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $prNumber) {
      reviewThreads(first: 100, after: $cursor) {
        nodes {
          id
          isResolved
          path
          line
          comments(last: 1) {
            nodes {
              url
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
"""


def _parse_repo(repo: str) -> tuple[str, str]:
    parts = repo.split("/", maxsplit=1)
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"Invalid repo '{repo}'. Expected OWNER/REPO format.")
    return parts[0], parts[1]


def _run_graphql(*, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        cmd.extend(["-F", f"{key}={value}"])

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(stderr or "gh api graphql failed")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Unable to parse gh api response as JSON") from exc


def _parse_thread(node: dict[str, Any]) -> ReviewThread:
    comment_nodes = node.get("comments", {}).get("nodes", [])
    url = comment_nodes[0].get("url") if comment_nodes else None
    return ReviewThread(
        thread_id=node["id"],
        is_resolved=bool(node["isResolved"]),
        path=node.get("path"),
        line=node.get("line"),
        url=url,
    )


def fetch_review_threads(repo: str, pr_number: int) -> list[ReviewThread]:
    owner, name = _parse_repo(repo)
    threads: list[ReviewThread] = []
    cursor: str | None = None

    while True:
        variables: dict[str, Any] = {"owner": owner, "name": name, "prNumber": pr_number}
        if cursor:
            variables["cursor"] = cursor

        payload = _run_graphql(query=QUERY, variables=variables)
        repository = payload.get("data", {}).get("repository")
        if not repository:
            raise RuntimeError("Repository not found in GraphQL response.")

        pr = repository.get("pullRequest")
        if not pr:
            raise RuntimeError(f"PR #{pr_number} not found in repository {repo}.")

        review_threads = pr.get("reviewThreads", {})
        for node in review_threads.get("nodes", []):
            threads.append(_parse_thread(node))

        page_info = review_threads.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return threads


def render_issue_comment(pr_number: int, unresolved_threads: list[ReviewThread]) -> str:
    lines = [
        f"Unresolved inline review threads for PR #{pr_number} ({len(unresolved_threads)} total):",
        "",
    ]
    if unresolved_threads:
        for index, thread in enumerate(unresolved_threads, start=1):
            lines.append(f"{index}. {thread.url or thread.thread_id}")
    else:
        lines.append("No unresolved inline review threads found.")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Repository in OWNER/REPO format.")
    parser.add_argument("--pr-number", required=True, type=int, help="Pull request number.")
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Fail when unresolved thread count does not match this value.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        help="Optional output path for unresolved thread JSON data.",
    )
    parser.add_argument(
        "--issue-comment-output",
        type=Path,
        help="Optional output path for a markdown issue comment listing thread links.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        all_threads = fetch_review_threads(args.repo, args.pr_number)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    unresolved_threads = [thread for thread in all_threads if not thread.is_resolved]

    print(f"PR #{args.pr_number} unresolved inline review threads: {len(unresolved_threads)}")
    for thread in unresolved_threads:
        print(f"- {thread.url or thread.thread_id}")

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "thread_id": thread.thread_id,
                "path": thread.path,
                "line": thread.line,
                "url": thread.url,
            }
            for thread in unresolved_threads
        ]
        args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.issue_comment_output:
        args.issue_comment_output.parent.mkdir(parents=True, exist_ok=True)
        args.issue_comment_output.write_text(
            render_issue_comment(args.pr_number, unresolved_threads), encoding="utf-8"
        )

    if args.expected_count is not None and len(unresolved_threads) != args.expected_count:
        print(
            f"Expected {args.expected_count} unresolved thread(s), "
            f"found {len(unresolved_threads)}.",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
