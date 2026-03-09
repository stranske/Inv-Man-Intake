#!/usr/bin/env python3
"""Extract unresolved PR review thread references and render a PR comment body."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReviewThreadRef:
    thread_id: str
    url: str


def _extract_thread_nodes(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")

    if "nodes" in payload and isinstance(payload["nodes"], list):
        return payload["nodes"]

    data = payload.get("data")
    if not isinstance(data, dict):
        return []

    repository = data.get("repository")
    if not isinstance(repository, dict):
        return []

    pull_request = repository.get("pullRequest")
    if not isinstance(pull_request, dict):
        return []

    review_threads = pull_request.get("reviewThreads")
    if not isinstance(review_threads, dict):
        return []

    nodes = review_threads.get("nodes")
    if isinstance(nodes, list):
        return nodes
    return []


def extract_unresolved_review_threads(payload: object) -> list[ReviewThreadRef]:
    """Return unresolved review thread references from a GraphQL payload."""
    refs: list[ReviewThreadRef] = []
    for node in _extract_thread_nodes(payload):
        if not isinstance(node, dict):
            continue
        if bool(node.get("isResolved")):
            continue

        thread_id = node.get("id")
        url = node.get("url")
        if not isinstance(thread_id, str) or not thread_id.strip():
            continue
        if not isinstance(url, str) or not url.strip():
            continue
        refs.append(ReviewThreadRef(thread_id=thread_id.strip(), url=url.strip()))

    refs.sort(key=lambda ref: ref.url)
    return refs


def render_unresolved_threads_comment(pr_number: int, refs: list[ReviewThreadRef]) -> str:
    """Render markdown for a PR comment listing unresolved review thread references."""
    if pr_number <= 0:
        raise ValueError("pr_number must be a positive integer")

    lines = [
        f"Unresolved inline review threads for PR #{pr_number}:",
        "",
    ]

    if not refs:
        lines.append("1. None found.")
    else:
        for index, ref in enumerate(refs, start=1):
            lines.append(f"{index}. {ref.url} (`{ref.thread_id}`)")

    lines.extend(
        [
            "",
            f"Total unresolved threads listed: {len(refs)}",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-json",
        type=Path,
        required=True,
        help="Path to JSON payload from GitHub reviewThreads GraphQL query.",
    )
    parser.add_argument("--pr-number", type=int, required=True, help="Pull request number.")
    parser.add_argument("--output", type=Path, required=True, help="Output markdown path.")
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Optional expected unresolved thread count. Fails on mismatch.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    refs = extract_unresolved_review_threads(payload)
    if args.expected_count is not None and len(refs) != args.expected_count:
        raise ValueError(f"Expected {args.expected_count} unresolved thread(s), found {len(refs)}.")
    comment = render_unresolved_threads_comment(args.pr_number, refs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(comment, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
