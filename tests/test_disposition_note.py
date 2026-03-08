from __future__ import annotations

from scripts.langchain.disposition_note import (
    extract_non_pass_provider_concerns,
    render_disposition_note,
    render_scope_lines,
)

SAMPLE_REPORT = """
## Provider Comparison Report

<details>
<summary>📋 Full Provider Details (click to expand)</summary>

#### openai
- **Model:** gpt-5
- **Verdict:** PASS
- **Confidence:** 88%
- **Summary:** Looks good.

#### github-models
- **Model:** gpt-4o
- **Verdict:** CONCERNS
- **Confidence:** 76%
- **Concerns:**
  - Missing explicit disposition link to issue #20.
  - Verify:compare non-PASS output not documented.

#### backup-provider
- **Model:** alt
- **Verdict:** FAIL
- **Confidence:** 55%
- **Summary:** Unable to confirm acceptance criteria.

</details>
"""


def test_extract_non_pass_provider_concerns_ignores_pass_and_captures_concerns() -> None:
    concerns = extract_non_pass_provider_concerns(SAMPLE_REPORT)
    assert len(concerns) == 2

    first = concerns[0]
    assert first.provider == "github-models"
    assert first.verdict == "CONCERNS"
    assert first.concerns == (
        "Missing explicit disposition link to issue #20.",
        "Verify:compare non-PASS output not documented.",
    )

    second = concerns[1]
    assert second.provider == "backup-provider"
    assert second.verdict == "FAIL"
    assert second.concerns == ()


def test_render_scope_lines_reports_when_provider_has_no_bullets() -> None:
    concerns = extract_non_pass_provider_concerns(SAMPLE_REPORT)
    scope_lines = render_scope_lines(concerns)
    assert "- github-models (CONCERNS): review 2 specific concern(s)." in scope_lines
    assert (
        "- backup-provider (FAIL): no explicit concern bullets; review provider summary."
        in scope_lines
    )


def test_render_disposition_note_includes_required_traceability_links() -> None:
    concerns = extract_non_pass_provider_concerns(SAMPLE_REPORT)
    note = render_disposition_note(
        pr_number=55,
        issue_number=88,
        source_issue_number=20,
        non_pass=concerns,
    )

    assert "# Verify:compare Disposition (PR #55)" in note
    assert "- Tracking issue: #88" in note
    assert "- Source issue: #20" in note
    assert "- References: #55, #88, #20" in note
