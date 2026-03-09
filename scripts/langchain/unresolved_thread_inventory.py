#!/usr/bin/env python3
"""Generate unresolved PR review thread inventory from GraphQL payload."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UnresolvedThread:
    """Normalized unresolved review thread metadata for disposition tracking."""

    thread_id: str
    path: str | None
    line: int | None
    url: str
    summary: str


def _normalize_summary(body: str, *, max_len: int = 180) -> str:
    collapsed = " ".join(body.split())
    if not collapsed:
        return "(no comment body)"
    if len(collapsed) <= max_len:
        return collapsed
    return f"{collapsed[: max_len - 1].rstrip()}…"


def extract_unresolved_threads(payload: dict[str, Any]) -> list[UnresolvedThread]:
    """Extract unresolved review threads from GitHub GraphQL response payload."""
    pull_request = payload.get("data", {}).get("repository", {}).get("pullRequest", {})
    raw_threads = pull_request.get("reviewThreads", {}).get("nodes", [])
    extracted: list[UnresolvedThread] = []

    for thread in raw_threads:
        if thread.get("isResolved", True):
            continue

        comments = thread.get("comments", {}).get("nodes", [])
        first_comment = comments[0] if comments else {}
        url = str(first_comment.get("url") or "").strip()
        if not url:
            continue

        summary = _normalize_summary(str(first_comment.get("body") or ""))
        line = thread.get("line")
        if line is None:
            line = thread.get("startLine")

        extracted.append(
            UnresolvedThread(
                thread_id=str(thread.get("id") or ""),
                path=thread.get("path"),
                line=int(line) if line is not None else None,
                url=url,
                summary=summary,
            )
        )
    return extracted


def render_unresolved_threads_comment(*, pr_number: int, threads: list[UnresolvedThread]) -> str:
    """Render markdown suitable for posting as a tracking comment on a PR."""
    lines = [
        f"Unresolved inline review thread inventory for PR #{pr_number}:",
        "",
        "| Thread | File | Line | Concern summary |",
        "| --- | --- | --- | --- |",
    ]

    for thread in threads:
        file_path = thread.path or "(unknown)"
        line_value = str(thread.line) if thread.line is not None else "(unknown)"
        lines.append(f"| {thread.url} | `{file_path}` | {line_value} | {thread.summary} |")

    if not threads:
        lines.append("| (none) | - | - | No unresolved threads found in payload. |")

    lines.extend(
        [
            "",
            f"Total unresolved threads captured: {len(threads)}",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_payload(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-file", required=True, help="Path to GitHub GraphQL JSON payload file"
    )
    parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    parser.add_argument("--output", help="Optional output markdown file path")
    parser.add_argument(
        "--expected-count",
        type=int,
        help="Fail if extracted unresolved thread count does not match this value",
    )
    args = parser.parse_args(argv)

    payload = _load_payload(args.input_file)
    threads = extract_unresolved_threads(payload)
    if args.expected_count is not None and len(threads) != args.expected_count:
        print(
            f"expected {args.expected_count} unresolved threads, found {len(threads)}",
        )
        return 1

    rendered = render_unresolved_threads_comment(pr_number=args.pr, threads=threads)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
