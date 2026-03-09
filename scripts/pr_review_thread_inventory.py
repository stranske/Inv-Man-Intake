#!/usr/bin/env python3
"""Generate unresolved PR review thread inventory/comment from GitHub GraphQL JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DISCUSSION_ID_PATTERN = re.compile(r"#discussion_r(\d+)")


@dataclass(frozen=True)
class ReviewThread:
    identifier: str
    url: str


def _review_thread_nodes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    root: Any = payload
    if "data" in payload:
        root = payload["data"]

    repository = root.get("repository") if isinstance(root, dict) else None
    pull_request = repository.get("pullRequest") if isinstance(repository, dict) else None
    if not isinstance(pull_request, dict):
        pull_request = root.get("pullRequest") if isinstance(root, dict) else None
    if not isinstance(pull_request, dict):
        raise ValueError("Could not find pullRequest data in input payload.")

    review_threads = pull_request.get("reviewThreads")
    if not isinstance(review_threads, dict):
        raise ValueError("Input payload does not contain pullRequest.reviewThreads.")

    nodes = review_threads.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("Input payload reviewThreads.nodes is not a list.")
    return nodes


def _first_comment(thread: dict[str, Any]) -> dict[str, Any]:
    comments = thread.get("comments")
    if not isinstance(comments, dict):
        return {}
    nodes = comments.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return {}
    first = nodes[0]
    return first if isinstance(first, dict) else {}


def _thread_identifier(thread: dict[str, Any]) -> str:
    comment = _first_comment(thread)
    database_id = comment.get("databaseId")
    if isinstance(database_id, int):
        return f"discussion_r{database_id}"

    comment_url = comment.get("url")
    if isinstance(comment_url, str):
        match = DISCUSSION_ID_PATTERN.search(comment_url)
        if match:
            return f"discussion_r{match.group(1)}"

    thread_id = thread.get("id")
    if isinstance(thread_id, str) and thread_id:
        return thread_id
    raise ValueError("Unable to determine review thread identifier.")


def _thread_url(thread: dict[str, Any], pr_url: str, identifier: str) -> str:
    comment = _first_comment(thread)
    comment_url = comment.get("url")
    if isinstance(comment_url, str) and comment_url:
        return comment_url

    thread_url = thread.get("url")
    if isinstance(thread_url, str) and thread_url:
        return thread_url

    if identifier.startswith("discussion_r"):
        return f"{pr_url}#{identifier}"
    return pr_url


def _sort_key(item: ReviewThread) -> tuple[int, int | str]:
    match = re.fullmatch(r"discussion_r(\d+)", item.identifier)
    if match:
        return (0, int(match.group(1)))
    return (1, item.identifier)


def extract_unresolved_threads(payload: dict[str, Any], *, pr_number: int) -> list[ReviewThread]:
    nodes = _review_thread_nodes(payload)
    pr_url = f"https://github.com/stranske/Inv-Man-Intake/pull/{pr_number}"
    unresolved: list[ReviewThread] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("isResolved") is True:
            continue

        identifier = _thread_identifier(node)
        url = _thread_url(node, pr_url=pr_url, identifier=identifier)
        unresolved.append(ReviewThread(identifier=identifier, url=url))

    return sorted(unresolved, key=_sort_key)


def render_pr_comment(*, pr_number: int, threads: list[ReviewThread]) -> str:
    lines = [
        f"Unresolved review thread inventory for PR #{pr_number}",
        "",
        f"Identified {len(threads)} unresolved inline review thread(s):",
    ]

    if not threads:
        lines.append("1. None found.")
    else:
        for index, thread in enumerate(threads, start=1):
            lines.append(f"{index}. `{thread.identifier}` - {thread.url}")
    return "\n".join(lines) + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="Path to GitHub GraphQL JSON payload."
    )
    parser.add_argument("--pr-number", type=int, required=True, help="Pull request number.")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output markdown file path for the generated PR comment text.",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Optional expected unresolved thread count. Command fails if actual count differs.",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    unresolved = extract_unresolved_threads(payload, pr_number=args.pr_number)

    if args.expected_count is not None and len(unresolved) != args.expected_count:
        print(
            "Unexpected unresolved thread count: "
            f"expected {args.expected_count}, found {len(unresolved)}.",
            file=sys.stderr,
        )
        return 1

    comment = render_pr_comment(pr_number=args.pr_number, threads=unresolved)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(comment, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
