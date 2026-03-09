"""Helpers for rendering verify:compare disposition comments."""

from __future__ import annotations


def _normalize_url(url: str | None, field_name: str) -> str:
    if not url or not url.strip():
        raise ValueError(f"{field_name} is required")
    return url.strip()


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


def format_verify_compare_outcome_note(
    *,
    disposition_url: str,
    source_issue: int,
    followup_reference: str | None = None,
) -> str:
    """Format a short outcome note linking disposition artifacts for PR/issue threads."""
    disposition_link = _normalize_url(disposition_url, "disposition_url")
    lines = [
        "## verify:compare Outcome",
        "",
        f"- Disposition note: {disposition_link}",
    ]
    if followup_reference and followup_reference.strip():
        lines.append(f"- Follow-up artifact: {followup_reference.strip()}")
    lines.append(f"- Source issue: #{source_issue}")
    return "\n".join(lines).strip() + "\n"
