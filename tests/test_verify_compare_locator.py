from pathlib import Path

from scripts.langchain.verify_compare_locator import (
    _as_scope,
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
