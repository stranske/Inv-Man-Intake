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


@dataclass(frozen=True)
class ThreadDisposition:
    thread_id: str
    rationale: str
    classification: str
    follow_up_pr_url: str | None = None


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


def load_thread_dispositions(payload: object) -> list[ThreadDisposition]:
    """Load per-thread disposition decisions from JSON content."""
    if not isinstance(payload, dict):
        raise ValueError("Disposition JSON payload must be an object")

    rows = payload.get("threads")
    if not isinstance(rows, list):
        raise ValueError("Disposition JSON payload must include a 'threads' list")

    dispositions: list[ThreadDisposition] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        thread_id = row.get("thread_id")
        rationale = row.get("rationale")
        classification = row.get("classification")
        follow_up_pr_url = row.get("follow_up_pr_url")

        if not isinstance(thread_id, str) or not thread_id.strip():
            continue
        if not isinstance(rationale, str) or not rationale.strip():
            continue
        if not isinstance(classification, str) or not classification.strip():
            continue
        if follow_up_pr_url is not None and not isinstance(follow_up_pr_url, str):
            continue

        dispositions.append(
            ThreadDisposition(
                thread_id=thread_id.strip(),
                rationale=rationale.strip(),
                classification=classification.strip(),
                follow_up_pr_url=follow_up_pr_url.strip() if follow_up_pr_url else None,
            )
        )

    dispositions.sort(key=lambda item: item.thread_id)
    return dispositions


def render_disposition_reply_comment(
    *,
    pr_number: int,
    refs: list[ReviewThreadRef],
    dispositions: list[ThreadDisposition],
) -> str:
    """Render a summary comment with per-thread disposition reply text."""
    if pr_number <= 0:
        raise ValueError("pr_number must be a positive integer")

    ref_ids = {ref.thread_id for ref in refs}
    disposition_map = {item.thread_id: item for item in dispositions}
    missing = sorted(ref_ids - set(disposition_map))
    if missing:
        raise ValueError(f"Missing disposition decision(s) for thread id(s): {', '.join(missing)}")

    ordered_refs = sorted(refs, key=lambda item: item.url)
    lines = [
        f"Disposition replies for unresolved inline review threads on PR #{pr_number}:",
        "",
    ]
    for index, ref in enumerate(ordered_refs, start=1):
        item = disposition_map[ref.thread_id]
        lines.extend(
            [
                f"{index}. {ref.url} (`{ref.thread_id}`)",
                f"   Classification: `{item.classification}`",
                f"   Rationale: {item.rationale}",
            ]
        )
        if item.follow_up_pr_url:
            lines.append(f"   Follow-up PR: {item.follow_up_pr_url}")
        lines.append("   Reply text: Acknowledged. " + item.rationale)
        if item.follow_up_pr_url:
            lines[-1] += f" Follow-up fix: {item.follow_up_pr_url}"
        lines.append("")

    lines.append(f"Total disposition replies drafted: {len(ordered_refs)}")
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
    parser.add_argument(
        "--dispositions-json",
        type=Path,
        help="Optional path to JSON with per-thread disposition decisions.",
    )
    parser.add_argument(
        "--dispositions-output",
        type=Path,
        help="Optional markdown output path for disposition reply comments.",
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

    if args.dispositions_json and args.dispositions_output:
        disposition_payload = json.loads(args.dispositions_json.read_text(encoding="utf-8"))
        decisions = load_thread_dispositions(disposition_payload)
        disposition_comment = render_disposition_reply_comment(
            pr_number=args.pr_number,
            refs=refs,
            dispositions=decisions,
        )
        args.dispositions_output.parent.mkdir(parents=True, exist_ok=True)
        args.dispositions_output.write_text(disposition_comment, encoding="utf-8")
    elif args.dispositions_json or args.dispositions_output:
        raise ValueError("--dispositions-json and --dispositions-output must be provided together.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
