"""Generate a markdown review note from exported pull request thread JSON."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ThreadComment:
    """Normalized unresolved-thread comment details."""

    url: str
    body: str
    reviewer: str
    path: str | None
    line: int | None


def _as_pull_request(payload: dict[str, Any]) -> dict[str, Any]:
    repository = payload.get("data", {}).get("repository", {})
    pull_request = repository.get("pullRequest")
    if not isinstance(pull_request, dict):
        raise ValueError("Expected payload.data.repository.pullRequest object")
    return pull_request


def extract_unresolved_thread_comments(payload: dict[str, Any]) -> list[ThreadComment]:
    """Return first comment from each unresolved review thread."""

    pull_request = _as_pull_request(payload)
    thread_nodes = pull_request.get("reviewThreads", {}).get("nodes", [])
    unresolved: list[ThreadComment] = []

    for thread in thread_nodes:
        if thread.get("isResolved"):
            continue
        comment_nodes = thread.get("comments", {}).get("nodes", [])
        if not comment_nodes:
            continue
        first_comment = comment_nodes[0]
        unresolved.append(
            ThreadComment(
                url=first_comment.get("url", "").strip(),
                body=first_comment.get("body", "").strip(),
                reviewer=(first_comment.get("author") or {}).get("login", "unknown"),
                path=first_comment.get("path"),
                line=first_comment.get("line"),
            )
        )

    return unresolved


def render_review_markdown(
    *,
    pr_number: int,
    issue_number: int,
    pr_url: str,
    comments: list[ThreadComment],
) -> str:
    lines = [
        f"# PR #{pr_number} Unresolved Thread Review",
        "",
        f"- Source PR: [#{pr_number}]({pr_url})",
        f"- Source issue: #{issue_number}",
        f"- Unresolved thread count at review time: {len(comments)}",
        "",
    ]

    if not comments:
        lines.extend(
            [
                "## Result",
                "No unresolved threads were found in the provided payload.",
            ]
        )
        return "\n".join(lines) + "\n"

    lines.append("## Threads")
    lines.append("")

    for index, comment in enumerate(comments, start=1):
        quote = comment.body.replace("\n", " ").strip()
        if len(quote) > 280:
            quote = f"{quote[:277]}..."

        lines.extend(
            [
                f"### Thread {index}",
                f"- Original review comment: [{comment.url}]({comment.url})",
                f"- Reviewer: `{comment.reviewer}`",
                f"- File context: `{comment.path or 'unknown'}`"
                + (f":{comment.line}" if comment.line else ""),
                f"- Quote: \"{quote or 'TODO: add quote from original review comment'}\"",
                "- Reviewer concern: TODO: summarize reviewer concern from thread discussion.",
                "- Disposition options:",
                "  - Fix: implement bounded code/test change and link follow-up PR.",
                "  - Defer: document rationale, owner, and timeline for deferred action.",
                "  - Reject: explain why the concern does not require a change.",
                "",
            ]
        )

    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a PR thread review markdown file from GraphQL thread JSON."
    )
    parser.add_argument("--input-json", type=Path, required=True, help="Path to JSON payload file.")
    parser.add_argument("--output", type=Path, required=True, help="Markdown output path.")
    parser.add_argument("--pr-number", type=int, required=True, help="Pull request number.")
    parser.add_argument("--pr-url", type=str, required=True, help="Pull request URL.")
    parser.add_argument("--issue-number", type=int, default=46, help="Related issue number.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    unresolved = extract_unresolved_thread_comments(payload)
    output = render_review_markdown(
        pr_number=args.pr_number,
        issue_number=args.issue_number,
        pr_url=args.pr_url,
        comments=unresolved,
    )
    args.output.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
