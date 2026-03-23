from pathlib import Path

from scripts.langchain.verify_compare_locator import (
    _as_decision,
    _as_disposition,
    _as_pr_note,
    _as_review,
    _as_scope,
    _as_validation,
    extract_non_pass_findings,
    scan_files,
)


def test_extract_non_pass_finding_for_target_pr() -> None:
    text = """
Review output for merged PR.
Source: [PR #54 verify:compare output](https://github.com/stranske/Inv-Man-Intake/pull/54#issuecomment-1234)
- Verdict: CONCERNS
- Confidence: 0.92
""".strip()

    findings = extract_non_pass_findings(text, source_file="verification_data.txt", pr_number=54)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.pr_number == 54
    assert finding.verdict == "CONCERNS"
    assert (
        finding.source_url == "https://github.com/stranske/Inv-Man-Intake/pull/54#issuecomment-1234"
    )
    assert "Verdict: CONCERNS" in finding.evidence_line


def test_extract_ignores_pass_verdict() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/pull/54#issuecomment-111
- Verdict: PASS
""".strip()

    findings = extract_non_pass_findings(text, source_file="verification_data.txt", pr_number=54)

    assert findings == []


def test_scan_files_collects_non_pass_without_pr_filter(tmp_path: Path) -> None:
    sample = tmp_path / "verification_data.txt"
    sample.write_text(
        """
Source: https://github.com/stranske/Inv-Man-Intake/pull/54#issuecomment-222
- Verdict: FAIL
""".strip(),
        encoding="utf-8",
    )

    findings = scan_files([sample])

    assert len(findings) == 1
    assert findings[0].pr_number == 54
    assert findings[0].verdict == "FAIL"


def test_extract_non_pass_phrase_with_pr_context() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/89
Source PR: #54
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue_context.txt", pr_number=54)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.pr_number == 54
    assert finding.verdict == "NON_PASS"
    assert finding.source_url == "https://github.com/stranske/Inv-Man-Intake/issues/89"
    assert "reported non-PASS output" in finding.evidence_line


def test_extract_non_pass_phrase_with_markdown_links_for_pr75() -> None:
    text = """
Source: [PR #75](https://github.com/stranske/Inv-Man-Intake/pull/75)
Source: [Issue #42](https://github.com/stranske/Inv-Man-Intake/issues/42)
verify:compare reported non-PASS output without a documented disposition for PR #75.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue_context.txt", pr_number=75)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.pr_number == 75
    assert finding.verdict == "NON_PASS"
    assert finding.source_url == "https://github.com/stranske/Inv-Man-Intake/issues/42"
    assert "reported non-PASS output without a documented disposition" in finding.evidence_line


def test_extract_ignores_non_verdict_concerns_wording() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/89
- [ ] Analyze the verify:compare output to determine if concerns are warranted
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue_context.txt", pr_number=54)

    assert findings == []


def test_scope_output_includes_disposition_requirements() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/89
Source PR: #54
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue_context.txt", pr_number=54)
    scope = _as_scope(findings, pr_number=54)

    assert "Disposition Scope For PR #54" in scope
    assert "https://github.com/stranske/Inv-Man-Intake/issues/89" in scope
    assert "reported non-PASS output without a documented disposition" in scope
    assert "2+ sentence rationale" in scope


def test_disposition_output_marks_documentation_only_gap() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/89
Source PR: #54
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue_context.txt", pr_number=54)
    disposition = _as_disposition(findings, pr_number=54)

    assert "Disposition note for PR #54" in disposition
    assert "https://github.com/stranske/Inv-Man-Intake/issues/89" in disposition
    assert "No code fixes are needed; documentation-only follow-up is required." in disposition
    assert "missing disposition record" in disposition


def test_disposition_output_marks_follow_up_fix_when_not_doc_gap() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/pull/54#issuecomment-222
- Verdict: FAIL
""".strip()

    findings = extract_non_pass_findings(text, source_file="verification_data.txt", pr_number=54)
    disposition = _as_disposition(findings, pr_number=54)

    assert "Disposition note for PR #54" in disposition
    assert "A bounded follow-up fix is needed" in disposition


def test_disposition_output_for_empty_findings() -> None:
    disposition = _as_disposition([], pr_number=54)

    assert "No disposition note can be generated" in disposition


def test_disposition_prefers_finding_with_source_link_when_multiple() -> None:
    text = """
`verify:compare reported non-PASS output without a documented disposition.`
| 54 | NON_PASS | https://github.com/stranske/Inv-Man-Intake/issues/89 | > verify:compare reported non-PASS output without a documented disposition. | codex-prompt-95.md |
""".strip()

    findings = extract_non_pass_findings(
        text, source_file="pr-54-verify-compare-output.md", pr_number=54
    )
    disposition = _as_disposition(findings, pr_number=54)

    assert "Evidence link: https://github.com/stranske/Inv-Man-Intake/issues/89" in disposition


def test_disposition_prefers_pr_issuecomment_link_when_available() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/89
Source: https://github.com/stranske/Inv-Man-Intake/pull/54#issuecomment-999
Source PR: #54
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue_context.txt", pr_number=54)
    disposition = _as_disposition(findings, pr_number=54)

    assert (
        "Evidence link: https://github.com/stranske/Inv-Man-Intake/pull/54#issuecomment-999"
        in disposition
    )


def test_disposition_doc_gap_rationale_uses_selected_pr_label() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/pull/77#issuecomment-123
Source PR: #77
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue_context.txt", pr_number=77)
    disposition = _as_disposition(findings, pr_number=77)

    assert "Adding a disposition note to PR #77 closes the verification gap" in disposition


def test_validation_output_passes_for_doc_gap_disposition() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/89
Source PR: #54
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue_context.txt", pr_number=54)
    validation = _as_validation(findings, pr_number=54)

    assert validation == "PASS: Disposition note satisfies required acceptance criteria."


def test_validation_output_fails_when_no_findings() -> None:
    validation = _as_validation([], pr_number=54)

    assert validation.startswith("FAIL: Disposition note is missing required criteria.")
    assert "Missing required evidence link" in validation
    assert "Missing clear statement on whether fixes are needed." in validation


def test_review_output_classifies_documentation_gap_for_pr86_style_signal() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/112
Source PR: #86
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue-112.txt", pr_number=86)
    review = _as_review(findings, pr_number=86)

    assert "## verify:compare Concern Review For PR #86" in review
    assert "Concern category: documentation gap" in review
    assert "Evidence link: https://github.com/stranske/Inv-Man-Intake/issues/112" in review
    assert "reported non-PASS output without a documented disposition" in review


def test_review_output_handles_empty_findings() -> None:
    review = _as_review([], pr_number=86)
    assert review == "No non-PASS verify:compare findings located for review."


def test_decision_output_marks_not_warranted_for_doc_gap_signal() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/112
Source PR: #86
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue-112.txt", pr_number=86)
    decision = _as_decision(findings, pr_number=86)

    assert "## verify:compare Concern Determination For PR #86" in decision
    assert "Concern category: documentation gap" in decision
    assert "Warranted: no (acceptable documentation-only outcome)." in decision


def test_decision_output_marks_warranted_for_fail_signal() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/pull/86#issuecomment-555
- Verdict: FAIL
""".strip()

    findings = extract_non_pass_findings(text, source_file="verification_data.txt", pr_number=86)
    decision = _as_decision(findings, pr_number=86)

    assert "## verify:compare Concern Determination For PR #86" in decision
    assert "Concern category: potential fix required" in decision
    assert "Warranted: yes (bounded follow-up fix required)." in decision


def test_decision_output_handles_empty_findings() -> None:
    decision = _as_decision([], pr_number=86)
    assert decision == "No non-PASS verify:compare findings located for decision."


def test_pr_note_output_for_doc_gap_signal() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/issues/112
Source PR: #86
verify:compare reported non-PASS output without a documented disposition.
""".strip()

    findings = extract_non_pass_findings(text, source_file="issue-112.txt", pr_number=86)
    note = _as_pr_note(findings, pr_number=86)

    assert "## verify:compare Disposition For PR #86" in note
    assert (
        "Summary: `verify:compare reported non-PASS output without a documented disposition.`"
        in note
    )
    assert "Concern warranted: no (documentation-only outcome is acceptable)." in note
    assert (
        "Connection: This note itself is the explanation for why no follow-up fix PR is needed."
        in note
    )
    assert "Follow-up PR reference: not required (no code fix warranted)." in note
    assert (
        "Remaining gaps issue: not required (no unresolved technical gaps remain after documentation)."
        in note
    )


def test_pr_note_output_for_fix_required_signal() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/pull/86#issuecomment-555
- Verdict: FAIL
""".strip()

    findings = extract_non_pass_findings(text, source_file="verification_data.txt", pr_number=86)
    note = _as_pr_note(findings, pr_number=86)

    assert "## verify:compare Disposition For PR #86" in note
    assert "Concern warranted: yes (bounded follow-up fix required)." in note
    assert "Link this note to a bounded follow-up PR" in note
    assert "Follow-up PR reference: required (add PR link once remediation is opened)." in note
    assert (
        "Remaining gaps issue: required if any concern is not fully addressed by the follow-up PR."
        in note
    )


def test_pr_note_output_for_fix_required_signal_with_links() -> None:
    text = """
Source: https://github.com/stranske/Inv-Man-Intake/pull/86#issuecomment-555
- Verdict: FAIL
""".strip()

    findings = extract_non_pass_findings(text, source_file="verification_data.txt", pr_number=86)
    note = _as_pr_note(
        findings,
        pr_number=86,
        follow_up_pr_url="https://github.com/stranske/Inv-Man-Intake/pull/201",
        remaining_gap_issue_url="https://github.com/stranske/Inv-Man-Intake/issues/202",
    )

    assert "Concern warranted: yes (bounded follow-up fix required)." in note
    assert "Follow-up PR reference: https://github.com/stranske/Inv-Man-Intake/pull/201" in note
    assert "Remaining gaps issue: https://github.com/stranske/Inv-Man-Intake/issues/202" in note
