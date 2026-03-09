#!/usr/bin/env python3
"""Helpers for documenting verify:compare non-PASS disposition notes."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderConcern:
    provider: str
    verdict: str
    concerns: tuple[str, ...]


@dataclass(frozen=True)
class ReviewItem:
    provider: str
    verdict: str
    summary: str


def extract_non_pass_provider_concerns(report: str) -> list[ProviderConcern]:
    """Extract non-PASS provider concerns from a comparison report markdown blob."""
    blocks = re.split(r"^####\s+", report, flags=re.MULTILINE)
    concerns: list[ProviderConcern] = []

    for block in blocks[1:]:
        lines = block.splitlines()
        if not lines:
            continue

        provider = lines[0].strip()
        verdict_match = re.search(r"- \*\*Verdict:\*\*\s*(PASS|CONCERNS|FAIL)\b", block)
        if not verdict_match:
            continue

        verdict = verdict_match.group(1)
        if verdict == "PASS":
            continue

        concern_items = re.findall(r"^\s{2}-\s+(.+?)\s*$", block, flags=re.MULTILINE)
        normalized = tuple(item.strip() for item in concern_items if item.strip())
        concerns.append(ProviderConcern(provider=provider, verdict=verdict, concerns=normalized))

    return concerns


def render_scope_lines(non_pass: list[ProviderConcern]) -> list[str]:
    """Render scoped review lines for a disposition note."""
    lines: list[str] = []
    for item in non_pass:
        if item.concerns:
            lines.append(
                f"- {item.provider} ({item.verdict}): review {len(item.concerns)} specific concern(s)."
            )
        else:
            lines.append(
                f"- {item.provider} ({item.verdict}): no explicit concern bullets; review provider summary."
            )
    return lines


def build_review_items(non_pass: list[ProviderConcern]) -> list[ReviewItem]:
    """Build deterministic, concern-by-concern review scope items."""
    items: list[ReviewItem] = []
    for concern in non_pass:
        if concern.concerns:
            for idx, text in enumerate(concern.concerns, start=1):
                items.append(
                    ReviewItem(
                        provider=concern.provider,
                        verdict=concern.verdict,
                        summary=f"Concern {idx}: {text}",
                    )
                )
            continue

        items.append(
            ReviewItem(
                provider=concern.provider,
                verdict=concern.verdict,
                summary="No explicit concern bullets; review provider summary text from PR artifact.",
            )
        )
    return items


def render_review_lines(non_pass: list[ProviderConcern]) -> list[str]:
    """Render markdown lines for specific review actions."""
    review_items = build_review_items(non_pass)
    if not review_items:
        return ["- No non-PASS items to review."]

    return [f"- {item.provider} ({item.verdict}): {item.summary}" for item in review_items]


def render_disposition_note(
    *,
    pr_number: int,
    issue_number: int,
    source_issue_number: int,
    non_pass: list[ProviderConcern],
) -> str:
    """Build markdown for a repository-tracked verify:compare disposition note."""
    lines = [
        f"# Verify:compare Disposition (PR #{pr_number})",
        "",
        "## Context",
        f"- PR: #{pr_number}",
        f"- Tracking issue: #{issue_number}",
        f"- Source issue: #{source_issue_number}",
        "",
        "## Scope Definition",
    ]

    scope = render_scope_lines(non_pass)
    if scope:
        lines.extend(scope)
    else:
        lines.append("- No non-PASS provider output detected in the supplied report.")

    lines.extend(
        [
            "",
            "## Focused Review Items",
        ]
    )
    lines.extend(render_review_lines(non_pass))

    lines.extend(
        [
            "",
            "## Disposition Path",
            "- Pending determination: `not-warranted rationale` or `follow-up fix`.",
            "",
            "## Traceability",
            f"- References: #{pr_number}, #{issue_number}, #{source_issue_number}",
            "",
        ]
    )
    return "\n".join(lines)


def _load_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-file", required=True, help="Path to provider comparison markdown")
    parser.add_argument("--pr", type=int, required=True, help="PR number")
    parser.add_argument("--issue", type=int, required=True, help="Tracking issue number")
    parser.add_argument(
        "--source-issue", type=int, required=True, help="Original source issue number"
    )
    parser.add_argument(
        "--output", required=True, help="Path for generated disposition note markdown"
    )
    args = parser.parse_args(argv)

    report = _load_text(args.report_file)
    non_pass = extract_non_pass_provider_concerns(report)
    note = render_disposition_note(
        pr_number=args.pr,
        issue_number=args.issue,
        source_issue_number=args.source_issue,
        non_pass=non_pass,
    )
    Path(args.output).write_text(note, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
