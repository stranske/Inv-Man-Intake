from pathlib import Path

from scripts.langchain.verify_compare_locator import (
    _as_disposition,
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
