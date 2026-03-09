"""Tests for extraction confidence threshold loading and enforcement."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.extraction.confidence import (
    attach_threshold_summary,
    evaluate_thresholds,
    load_threshold_config,
)
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "extraction_thresholds.yaml"


def _result(*fields: tuple[str, float]) -> ExtractedDocumentResult:
    return ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="primary",
        fields=tuple(
            ExtractedField(
                key=key,
                value="value",
                confidence=confidence,
                source_doc_id="doc_1",
                source_page=1,
            )
            for key, confidence in fields
        ),
    )


def test_load_threshold_config_reads_policy_values() -> None:
    config = load_threshold_config(_CONFIG_PATH)

    assert config.field_auto_accept_min == 0.85
    assert config.key_field_confidence_min == 0.75
    assert config.document_key_field_coverage_min == 0.80
    assert config.mandatory_field_min == 0.60
    assert "terms.management_fee" in config.mandatory_fields


def test_evaluate_thresholds_boundary_values_are_deterministic() -> None:
    config = load_threshold_config(_CONFIG_PATH)
    result = _result(
        ("terms.management_fee", 0.85),
        ("performance.net_return_1y", 0.75),
        ("operations.aum", 0.60),
        ("other.field", 0.40),
    )

    decision = evaluate_thresholds(
        result=result,
        key_fields=(
            "terms.management_fee",
            "performance.net_return_1y",
            "operations.aum",
            "other.field",
        ),
        config=config,
    )

    assert set(decision.auto_accept_fields) == {"terms.management_fee"}
    assert decision.key_field_coverage_ratio == 0.5
    assert decision.auto_pass_document is False
    assert decision.escalate is True
    assert decision.escalation_reason == "low_key_field_coverage"


def test_evaluate_thresholds_escalates_when_mandatory_field_below_floor() -> None:
    config = load_threshold_config(_CONFIG_PATH)
    result = _result(
        ("terms.management_fee", 0.95),
        ("performance.net_return_1y", 0.90),
        ("operations.aum", 0.59),
    )

    decision = evaluate_thresholds(
        result=result,
        key_fields=(
            "terms.management_fee",
            "performance.net_return_1y",
            "operations.aum",
        ),
        config=config,
    )

    assert decision.auto_pass_document is False
    assert decision.escalate is True
    assert decision.escalation_reason == "confidence_below_threshold:operations.aum"


def test_evaluate_thresholds_escalates_when_mandatory_field_is_missing() -> None:
    config = load_threshold_config(_CONFIG_PATH)
    result = _result(
        ("terms.management_fee", 0.95),
        ("performance.net_return_1y", 0.91),
    )

    decision = evaluate_thresholds(
        result=result,
        key_fields=(
            "terms.management_fee",
            "performance.net_return_1y",
        ),
        config=config,
    )

    assert decision.escalate is True
    assert decision.escalation_reason == "missing_mandatory_field:operations.aum"


def test_attach_threshold_summary_adds_document_policy_fields() -> None:
    config = load_threshold_config(_CONFIG_PATH)
    result = _result(
        ("terms.management_fee", 0.95),
        ("performance.net_return_1y", 0.91),
        ("operations.aum", 0.90),
    )
    decision = evaluate_thresholds(
        result=result,
        key_fields=(
            "terms.management_fee",
            "performance.net_return_1y",
            "operations.aum",
        ),
        config=config,
    )

    updated = attach_threshold_summary(result=result, decision=decision)
    by_key = {field.key: field for field in updated.fields}

    assert by_key["confidence.document.auto_pass"].value == "true"
    assert by_key["confidence.document.escalation_reason"].value == "none"


def test_evaluate_thresholds_empty_key_fields_forces_escalation() -> None:
    config = load_threshold_config(_CONFIG_PATH)
    result = _result(
        ("terms.management_fee", 0.95),
        ("performance.net_return_1y", 0.91),
        ("operations.aum", 0.90),
    )

    decision = evaluate_thresholds(result=result, key_fields=(), config=config)

    assert decision.key_field_coverage_ratio == 0.0
    assert decision.auto_pass_document is False
    assert decision.escalate is True
    assert decision.escalation_reason == "low_key_field_coverage"
