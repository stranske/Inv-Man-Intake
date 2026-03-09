"""Tests for verify:compare disposition formatting helpers."""

from __future__ import annotations

import pytest

from scripts.langchain.disposition import format_verify_compare_disposition


def test_format_disposition_not_warranted_includes_required_text() -> None:
    rendered = format_verify_compare_disposition(
        concerns_warranted=False,
        rationale="The non-PASS result was due to advisory-only wording, not a correctness gap.",
        evidence_url="https://github.com/org/repo/actions/runs/123",
        source_issue=29,
    )

    assert "## verify:compare Disposition" in rendered
    assert "concerns not warranted:" in rendered
    assert "verify:compare output" in rendered
    assert "Source issue: #29" in rendered


def test_format_disposition_warranted_uses_followup_reference() -> None:
    rendered = format_verify_compare_disposition(
        concerns_warranted=True,
        followup_number=123,
        evidence_url="https://github.com/org/repo/pull/51",
    )

    assert "concerns warranted: see #123" in rendered
    assert "verify:compare output" in rendered


def test_not_warranted_requires_rationale() -> None:
    with pytest.raises(ValueError, match="rationale is required"):
        format_verify_compare_disposition(concerns_warranted=False)


def test_warranted_requires_followup_number() -> None:
    with pytest.raises(ValueError, match="followup_number is required"):
        format_verify_compare_disposition(concerns_warranted=True)
