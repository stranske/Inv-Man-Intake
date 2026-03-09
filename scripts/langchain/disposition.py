"""Helpers for rendering verify:compare disposition comments."""

from __future__ import annotations


def format_verify_compare_disposition(
    *,
    concerns_warranted: bool,
    rationale: str | None = None,
    followup_number: int | None = None,
    evidence_url: str | None = None,
    source_issue: int | None = None,
) -> str:
    """Format a standard verify:compare disposition comment for PR threads."""
    lines = ["## verify:compare Disposition", ""]
    if concerns_warranted:
        if followup_number is None:
            raise ValueError("followup_number is required when concerns_warranted is True")
        lines.append(f"concerns warranted: see #{followup_number}")
    else:
        if not rationale or not rationale.strip():
            raise ValueError("rationale is required when concerns_warranted is False")
        lines.append(f"concerns not warranted: {rationale.strip()}")

    lines.append("")
    if evidence_url:
        lines.append(f"- verify:compare output: {evidence_url}")
    if source_issue is not None:
        lines.append(f"- Source issue: #{source_issue}")
    return "\n".join(lines).strip() + "\n"
