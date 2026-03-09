from __future__ import annotations

import pytest

from scripts.langchain.disposition_note import (
    DispositionDecision,
    build_review_items,
    extract_non_pass_provider_concerns,
    main,
    render_disposition_note,
    render_review_lines,
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
    assert second.summary == "Unable to confirm acceptance criteria."


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
    assert "## Focused Review Items" in note
    assert (
        "- github-models (CONCERNS): Concern 1: Missing explicit disposition link to issue #20."
        in note
    )
    assert (
        "- backup-provider (FAIL): Summary-only concern: Unable to confirm acceptance criteria."
        in note
    )
    assert "- References: #55, #88, #20" in note


def test_build_review_items_emits_per_concern_and_summary_fallback() -> None:
    concerns = extract_non_pass_provider_concerns(SAMPLE_REPORT)
    items = build_review_items(concerns)

    assert len(items) == 3
    assert items[0].provider == "github-models"
    assert items[0].summary == "Concern 1: Missing explicit disposition link to issue #20."
    assert items[1].summary == "Concern 2: Verify:compare non-PASS output not documented."
    assert items[2].provider == "backup-provider"
    assert items[2].summary == "Summary-only concern: Unable to confirm acceptance criteria."


def test_render_review_lines_reports_no_work_when_all_providers_pass() -> None:
    assert render_review_lines([]) == ["- No non-PASS items to review."]


def test_render_disposition_note_supports_not_warranted_path() -> None:
    concerns = extract_non_pass_provider_concerns(SAMPLE_REPORT)
    note = render_disposition_note(
        pr_number=55,
        issue_number=88,
        source_issue_number=20,
        non_pass=concerns,
        decision=DispositionDecision(
            path="not-warranted",
            why="Provider concern duplicates already-resolved formatting guidance.",
        ),
    )

    assert "- Path chosen: `not-warranted rationale`." in note
    assert "- Why: Provider concern duplicates already-resolved formatting guidance." in note
    assert "Follow-up fix reference" not in note


def test_render_disposition_note_supports_follow_up_fix_path() -> None:
    concerns = extract_non_pass_provider_concerns(SAMPLE_REPORT)
    note = render_disposition_note(
        pr_number=55,
        issue_number=88,
        source_issue_number=20,
        non_pass=concerns,
        decision=DispositionDecision(
            path="follow-up-fix",
            why="Concern is valid and requires repository-tracked remediation.",
            follow_up_ref="commit 29fe4e0",
        ),
    )

    assert "- Path chosen: `follow-up fix`." in note
    assert "- Why: Concern is valid and requires repository-tracked remediation." in note
    assert "- Follow-up fix reference: commit 29fe4e0" in note


def test_main_requires_why_for_decision_path(tmp_path) -> None:
    report_path = tmp_path / "report.md"
    output_path = tmp_path / "note.md"
    report_path.write_text(SAMPLE_REPORT, encoding="utf-8")

    with pytest.raises(SystemExit):
        main(
            [
                "--report-file",
                str(report_path),
                "--pr",
                "55",
                "--issue",
                "88",
                "--source-issue",
                "20",
                "--output",
                str(output_path),
                "--decision-path",
                "not-warranted",
            ]
        )


def test_main_requires_follow_up_ref_for_follow_up_fix_path(tmp_path) -> None:
    report_path = tmp_path / "report.md"
    output_path = tmp_path / "note.md"
    report_path.write_text(SAMPLE_REPORT, encoding="utf-8")

    with pytest.raises(SystemExit):
        main(
            [
                "--report-file",
                str(report_path),
                "--pr",
                "55",
                "--issue",
                "88",
                "--source-issue",
                "20",
                "--output",
                str(output_path),
                "--decision-path",
                "follow-up-fix",
                "--decision-why",
                "Concern is valid and needs a fix.",
            ]
        )
