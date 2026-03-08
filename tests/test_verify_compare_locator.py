from pathlib import Path

from scripts.langchain.verify_compare_locator import extract_non_pass_findings, scan_files


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
