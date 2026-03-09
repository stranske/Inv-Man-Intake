"""Tests for verify:compare evidence extraction in follow-up issue generation."""

from __future__ import annotations

from scripts.langchain.followup_issue_generator import (
    OriginalIssueData,
    extract_verification_data,
    generate_disposition_comment,
    generate_followup_issue,
    generate_issue_disposition_link_comment,
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
    assert "non-PASS output requires code changes: **yes**" in followup.body
    assert "requires code changes: **yes**" in followup.body
    assert "## verify:compare Evidence" in followup.body
    assert "Provider=openai; Model=gpt-5; Verdict=FAIL; Confidence=60%" in followup.body


def test_generate_followup_issue_marks_advisory_non_pass_as_no_code_change() -> None:
    comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | CONCERNS | 64% | Style nit in docs wording |
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

    assert (
        "Provider=openai; Verdict=CONCERNS; Difference=Style nit in docs wording" in followup.body
    )
    assert "non-PASS output requires code changes: **no**" in followup.body
    assert "requires code changes: **no**" in followup.body


def test_generate_followup_issue_marks_low_confidence_concerns_as_disposition_only() -> None:
    comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | PASS | 92% | Looks good |
| anthropic | claude-3.7 | CONCERNS | 64% | Ambiguous wording preference |
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

    assert "non-PASS output requires code changes: **no**" in followup.body
    assert "requires code changes: **no**" in followup.body
    assert "low-confidence and contradicted by high-confidence PASS provider(s)" in followup.body


def test_generate_followup_issue_keeps_fail_as_code_change_required() -> None:
    comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | PASS | 95% | Looks good |
| anthropic | claude-3.7 | FAIL | 52% | Regression in parser behavior |
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

    assert "non-PASS output requires code changes: **yes**" in followup.body
    assert (
        "requires code changes: **yes**; technical rationale: Difference describes a functional "
        "defect or regression signal that should be resolved in code." in followup.body
    )


def test_generate_disposition_comment_includes_evidence_decision_and_rationale() -> None:
    comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | FAIL | 60% | Regression in parsing |
"""
    verification_data = extract_verification_data(comment)

    disposition = generate_disposition_comment(verification_data, pr_number=49)

    assert "## verify:compare Disposition" in disposition
    assert "Source: verify:compare non-PASS output from PR #49" in disposition
    assert "`Provider=openai; Model=gpt-5; Verdict=FAIL; Confidence=60%`" in disposition
    assert "non-PASS output requires code changes: **yes**" in disposition
    assert "technical rationale: Difference describes a functional defect" in disposition


def test_generate_disposition_comment_includes_source_link_when_provided() -> None:
    comment = """
## Provider Comparison Report

### Provider Summary
| Provider | Model | Verdict | Confidence | Summary |
| --- | --- | --- | --- | --- |
| openai | gpt-5 | CONCERNS | 74% | Missing edge case |
"""
    verification_data = extract_verification_data(comment)

    disposition = generate_disposition_comment(
        verification_data,
        pr_number=49,
        source_url="https://github.com/stranske/Inv-Man-Intake/pull/49#issuecomment-123",
    )

    assert "Source: verify:compare non-PASS output from PR #49" in disposition
    assert (
        "Source link: https://github.com/stranske/Inv-Man-Intake/pull/49#issuecomment-123"
        in disposition
    )


def test_generate_issue_disposition_link_comment_includes_url() -> None:
    body = generate_issue_disposition_link_comment(
        disposition_url="https://github.com/stranske/Inv-Man-Intake/pull/49#issuecomment-123"
    )

    assert "Disposition documentation for verify:compare is recorded here" in body
    assert "https://github.com/stranske/Inv-Man-Intake/pull/49#issuecomment-123" in body
