"""Tests for correction-backed extraction calibration reporting."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.data.provenance import CorrectionRecord, ExtractedFieldRecord
from inv_man_intake.extraction.confidence import ThresholdConfig
from inv_man_intake.readiness.extraction_calibration import build_calibration_report


def test_calibration_metrics_on_seeded_corrections(tmp_path: Path) -> None:
    threshold_path = tmp_path / "extraction_thresholds.yaml"
    threshold_path.write_text("field_auto_accept_min: 0.85\n", encoding="utf-8")
    before_thresholds = threshold_path.read_text(encoding="utf-8")

    report = build_calibration_report(
        extracted_fields=(
            _field("field-aum", "operations.aum", "100000000", 0.9),
            _field("field-fee", "terms.management_fee", "1.00%", 0.9),
            _field("field-strategy", "strategy.asset_class", "Private Equity", 0.9),
        ),
        corrections=(
            CorrectionRecord(
                correction_id=1,
                field_id="field-aum",
                corrected_value="100000000",
                reason="confirmed",
                corrected_by="analyst@example.com",
                corrected_at="2026-07-04T10:00:00Z",
            ),
            CorrectionRecord(
                correction_id=2,
                field_id="field-fee",
                corrected_value="1.25%",
                reason="manager ppm correction",
                corrected_by="analyst@example.com",
                corrected_at="2026-07-04T10:05:00Z",
            ),
            CorrectionRecord(
                correction_id=3,
                field_id="field-strategy",
                corrected_value="Private Equity",
                reason="confirmed",
                corrected_by="analyst@example.com",
                corrected_at="2026-07-04T10:10:00Z",
            ),
        ),
        expected_field_keys=("operations.aum", "terms.management_fee", "strategy.asset_class"),
        threshold_config=ThresholdConfig(
            field_auto_accept_min=0.85,
            key_field_confidence_min=0.75,
            document_key_field_coverage_min=0.8,
            mandatory_field_min=0.6,
            mandatory_fields=("operations.aum",),
        ),
    )

    assert report["summary"] == {
        "field_count": 3,
        "expected_field_count": 3,
        "true_positive_count": 2,
        "false_positive_count": 1,
        "false_negative_count": 0,
        "precision": 0.6667,
        "recall": 1.0,
        "auto_accept_precision": 0.6667,
        "missing_expected_fields": [],
    }
    assert report["field_metrics"]["terms.management_fee"]["precision"] == 0.0
    assert report["confidence_buckets"] == [
        {
            "bucket": "0.85-1.00",
            "count": 3,
            "mean_confidence": 0.9,
            "observed_accuracy": 0.6667,
            "calibration_gap": 0.2333,
        }
    ]
    assert report["threshold_suggestions"]["field_auto_accept_min"] == {
        "current": 0.85,
        "direction": "raise",
        "basis": "auto_accept_precision",
        "observed": 0.6667,
    }
    assert threshold_path.read_text(encoding="utf-8") == before_thresholds


def _field(field_id: str, key: str, value: str, confidence: float) -> ExtractedFieldRecord:
    return ExtractedFieldRecord(
        field_id=field_id,
        document_id="doc-1",
        field_key=key,
        value=value,
        confidence=confidence,
        source_page=1,
        source_snippet=None,
        extracted_at="2026-07-04T09:00:00Z",
    )
