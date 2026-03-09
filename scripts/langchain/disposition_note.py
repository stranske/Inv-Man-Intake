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
    summary: str | None = None


@dataclass(frozen=True)
class ReviewItem:
    provider: str
    verdict: str
    summary: str


@dataclass(frozen=True)
class DispositionDecision:
    path: str
    why: str
    follow_up_ref: str | None = None


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
        summary_match = re.search(r"- \*\*Summary:\*\*\s*(.+?)\s*$", block, flags=re.MULTILINE)
        summary = summary_match.group(1).strip() if summary_match else None
        concerns.append(
            ProviderConcern(
                provider=provider,
                verdict=verdict,
                concerns=normalized,
                summary=summary,
            )
        )

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
                summary=(
                    f"Summary-only concern: {concern.summary}"
                    if concern.summary
                    else "No explicit concern bullets; review provider summary text from PR artifact."
                ),
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
    decision: DispositionDecision | None = None,
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
        ]
    )

    if decision is None:
        lines.append("- Pending determination: `not-warranted rationale` or `follow-up fix`.")
    elif decision.path == "not-warranted":
        lines.append("- Path chosen: `not-warranted rationale`.")
        lines.append(f"- Why: {decision.why}")
    else:
        lines.append("- Path chosen: `follow-up fix`.")
        lines.append(f"- Why: {decision.why}")
        if decision.follow_up_ref:
            lines.append(f"- Follow-up fix reference: {decision.follow_up_ref}")

    lines.extend(
        [
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
    parser.add_argument(
        "--decision-path",
        choices=("not-warranted", "follow-up-fix"),
        help="Disposition decision path to record in the note",
    )
    parser.add_argument("--decision-why", help="Rationale explaining the chosen disposition path")
    parser.add_argument(
        "--follow-up-ref",
        help="Follow-up PR/commit reference when --decision-path=follow-up-fix",
    )
    args = parser.parse_args(argv)

    decision: DispositionDecision | None = None
    if args.decision_path:
        if not args.decision_why:
            parser.error("--decision-why is required when --decision-path is provided")
        if args.decision_path == "follow-up-fix" and not args.follow_up_ref:
            parser.error("--follow-up-ref is required when --decision-path=follow-up-fix")
        decision = DispositionDecision(
            path="not-warranted" if args.decision_path == "not-warranted" else "follow-up-fix",
            why=args.decision_why.strip(),
            follow_up_ref=args.follow_up_ref.strip() if args.follow_up_ref else None,
        )

    report = _load_text(args.report_file)
    non_pass = extract_non_pass_provider_concerns(report)
    note = render_disposition_note(
        pr_number=args.pr,
        issue_number=args.issue,
        source_issue_number=args.source_issue,
        non_pass=non_pass,
        decision=decision,
    )
    Path(args.output).write_text(note, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
