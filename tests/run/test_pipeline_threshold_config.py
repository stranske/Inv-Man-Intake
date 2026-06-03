"""Tests for production threshold-config wiring (#518)."""

from __future__ import annotations

import json
from pathlib import Path

from inv_man_intake.extraction.confidence import load_threshold_config
from inv_man_intake.run import DEFAULT_THRESHOLD_CONFIG_PATH, run_pipeline

_BUNDLE = Path("tests/fixtures/intake/pdf_primary_mixed_bundle.json")
_MANDATORY_FIELDS = {
    "terms.management_fee",
    "performance.net_return_1y",
    "operations.aum",
}


def test_yaml_mandatory_fields_match_v1_contract() -> None:
    config = load_threshold_config(DEFAULT_THRESHOLD_CONFIG_PATH)

    assert set(config.mandatory_fields) == _MANDATORY_FIELDS


def test_run_pipeline_uses_yaml_mandatory_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "strict-thresholds.yaml"
    config_path.write_text(
        "\n".join(
            [
                "field_auto_accept_min: 0.85",
                "key_field_confidence_min: 0.75",
                "document_key_field_coverage_min: 0.80",
                "mandatory_field_min: 0.80",
                "mandatory_fields:",
                "  - terms.management_fee",
                "  - performance.net_return_1y",
                "  - operations.aum",
                "",
            ]
        ),
        encoding="utf-8",
    )

    output_dir = tmp_path / "out"
    run_pipeline(_BUNDLE, output_dir=output_dir, threshold_config_path=config_path)

    summary = json.loads((output_dir / "threshold-summary.json").read_text(encoding="utf-8"))

    assert summary["escalate"] is True
    assert summary["escalation_reason"] == "confidence_below_threshold:operations.aum"
    assert (
        summary["document"]["confidence.document.escalation_reason"]
        == "confidence_below_threshold:operations.aum"
    )
