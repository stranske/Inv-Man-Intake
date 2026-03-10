#!/usr/bin/env python3
"""Build a markdown review/disposition scaffold from GitHub review-thread JSON."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReviewThread:
    thread_id: str | None
    thread_url: str
    comment_url: str | None
    path: str | None
    line: int | None
    is_resolved: bool
    concern_excerpt: str

    @property
    def thread_ref(self) -> str:
        if self.thread_id:
            return self.thread_id
        match = re.search(r"(discussion_r\d+)", self.thread_url)
        if match:
            return match.group(1)
        return self.thread_url


def _as_excerpt(text: str | None, *, max_len: int = 160) -> str:
    if not text:
        return "No comment body available in payload."
    normalized = " ".join(text.split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 3].rstrip() + "..."


def _from_thread_node(node: dict[str, Any]) -> ReviewThread:
    comments = node.get("comments") or {}
    comment_nodes = comments.get("nodes") if isinstance(comments, dict) else None
    first_comment = comment_nodes[0] if comment_nodes else {}

    thread_url = node.get("url") or first_comment.get("url")
    if not isinstance(thread_url, str) or not thread_url.strip():
        raise ValueError("Review thread is missing a usable url")

    line_value = first_comment.get("line")
    if line_value is None:
        line_value = first_comment.get("originalLine")
    if not isinstance(line_value, int):
        line_value = None

    return ReviewThread(
        thread_id=node.get("id") if isinstance(node.get("id"), str) else None,
        thread_url=thread_url.strip(),
        comment_url=first_comment.get("url") if isinstance(first_comment.get("url"), str) else None,
        path=first_comment.get("path") if isinstance(first_comment.get("path"), str) else None,
        line=line_value,
        is_resolved=bool(node.get("isResolved", False)),
        concern_excerpt=_as_excerpt(
            first_comment.get("body") if isinstance(first_comment.get("body"), str) else None
        ),
    )


def _extract_thread_nodes(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [node for node in payload if isinstance(node, dict)]

    if not isinstance(payload, dict):
        raise ValueError("Unsupported JSON structure for review threads")

    threads = payload.get("threads")
    if isinstance(threads, list):
        return [node for node in threads if isinstance(node, dict)]

    graphql_nodes = (
        payload.get("data", {})
        .get("repository", {})
        .get("pullRequest", {})
        .get("reviewThreads", {})
        .get("nodes")
    )
    if isinstance(graphql_nodes, list):
        return [node for node in graphql_nodes if isinstance(node, dict)]

    raise ValueError("Could not find review thread nodes in payload")


def extract_review_threads(payload: Any) -> list[ReviewThread]:
    """Extract typed review threads from JSON payload."""
    threads = [_from_thread_node(node) for node in _extract_thread_nodes(payload)]
    # Keep deterministic order for generated docs.
    return sorted(threads, key=lambda thread: thread.thread_url)


def render_unresolved_thread_report(
    *,
    pr_number: int,
    source_issue: int | None,
    tracking_issue: int | None,
    threads: list[ReviewThread],
) -> str:
    """Render markdown scaffold for unresolved-thread review/disposition."""
    lines: list[str] = [f"# PR #{pr_number} Unresolved Review Threads", ""]
    if source_issue is not None:
        lines.append(f"Source issue: #{source_issue}  ")
    if tracking_issue is not None:
        lines.append(f"Tracking issue: #{tracking_issue}  ")
    lines.extend(["", "## Thread Inventory", ""])
    lines.append(
        "| Thread URL | File | Line | Concern Excerpt | Classification | Rationale | Disposition |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")

    for thread in threads:
        file_path = thread.path or "-"
        line_str = str(thread.line) if thread.line is not None else "-"
        lines.append(
            f"| {thread.thread_url} | {file_path} | {line_str} | "
            f"{thread.concern_excerpt} | TODO | TODO | TODO |"
        )

    lines.extend(
        [
            "",
            "## Summary Comment Draft",
            "",
            "Thread dispositions for previously unresolved review items:",
        ]
    )
    for thread in threads:
        lines.append(f"- `{thread.thread_ref}`: `TODO` (classification/rationale/disposition).")

    lines.extend(
        [
            "",
            "## Validation Checklist",
            "",
            "- [ ] Reviewed each unresolved thread and copied concern content.",
            "- [ ] Classified each thread: `warranted-fix` or `not-warranted`.",
            "- [ ] Added disposition rationale for every thread.",
            "- [ ] Posted one summary comment and one reply per thread on the PR.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threads-json", required=True, help="Path to review-thread JSON payload")
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument("--output", required=True, help="Path for generated markdown")
    parser.add_argument("--source-issue", type=int, help="Source issue number")
    parser.add_argument("--issue", type=int, help="Tracking issue number")
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="Include resolved threads in generated output",
    )
    args = parser.parse_args(argv)

    payload = _load_json(args.threads_json)
    threads = extract_review_threads(payload)
    if not args.include_resolved:
        threads = [thread for thread in threads if not thread.is_resolved]

    report = render_unresolved_thread_report(
        pr_number=args.pr,
        source_issue=args.source_issue,
        tracking_issue=args.issue,
        threads=threads,
    )
    Path(args.output).write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
