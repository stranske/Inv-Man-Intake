"""Tests for verify:compare evidence extraction in follow-up issue generation."""

from __future__ import annotations

from scripts.langchain.followup_issue_generator import (
    OriginalIssueData,
    extract_verification_data,
    generate_followup_issue,
)


def test_extract_verification_data_captures_non_pass_rows() -> None:
    comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | PASS | 92% | Looks good |
| anthropic | claude-3.7 | CONCERNS | 74% | Missing edge case |
"""

    data = extract_verification_data(comment)

    assert data.non_pass_output == [
        "Provider=anthropic; Model=claude-3.7; Verdict=CONCERNS; Confidence=74%"
    ]
    assert data.non_pass_findings == [
        "Provider=anthropic; Verdict=CONCERNS; Difference=Missing edge case"
    ]


def test_generate_followup_issue_includes_verify_compare_evidence_section() -> None:
    comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | FAIL | 60% | Regression in parsing |
"""
    verification_data = extract_verification_data(comment)
    original_issue = OriginalIssueData(
        title="Issue title",
        number=92,
        acceptance_criteria=["Disposition comment includes technical justification"],
    )

    followup = generate_followup_issue(
        verification_data,
        original_issue,
        pr_number=49,
        use_llm=False,
    )

    assert "## verify:compare Analysis" in followup.body
    assert "Provider=openai; Verdict=FAIL; Difference=Regression in parsing" in followup.body
    assert "## verify:compare Evidence" in followup.body
    assert "Provider=openai; Model=gpt-5; Verdict=FAIL; Confidence=60%" in followup.body
