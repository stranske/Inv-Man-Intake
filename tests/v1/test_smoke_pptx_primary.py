"""End-to-end v1 smoke coverage for the PPTX-primary intake bundle."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.v1_smoke import run_v1_smoke_pipeline


def test_pptx_primary_bundle_reaches_scoring_without_escalation() -> None:
    artifacts = run_v1_smoke_pipeline(
        fixture_root=Path("tests/fixtures/intake"),
        intake_bundle_file="pptx_primary_mixed_bundle.json",
        package_id="pkg_pptx_mixed_001",
        expected_document_ids=(
            "pkg_pptx_mixed_001:doc:0",
            "pkg_pptx_mixed_001:doc:1",
            "pkg_pptx_mixed_001:doc:2",
        ),
    )

    assert artifacts.extraction_with_thresholds.provider_name == "pptx-primary"
    assert artifacts.score.final_score is not None
    assert artifacts.threshold_decision.escalate is False
