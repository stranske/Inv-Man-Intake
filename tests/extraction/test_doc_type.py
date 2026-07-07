"""Tests for document-type-specific extraction threshold profiles."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.extraction.confidence import (
    evaluate_thresholds,
    load_threshold_config,
    select_threshold_profile,
)
from inv_man_intake.extraction.doc_type import DocumentType, classify_doc_type
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "extraction_thresholds.yaml"
_GLOBAL_KEY_FIELDS = (
    "terms.management_fee",
    "performance.net_return_1y",
    "operations.aum",
)


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
                method="primary",
            )
            for key, confidence in fields
        ),
    )


def test_doctype_selects_expected_field_profile() -> None:
    config = load_threshold_config(_CONFIG_PATH)
    document_type = classify_doc_type("Q2 manager tear sheet with returns and AUM")
    key_fields, profile_config = select_threshold_profile(
        document_type=document_type,
        key_fields=_GLOBAL_KEY_FIELDS,
        config=config,
    )

    tear_sheet_decision = evaluate_thresholds(
        result=_result(
            ("performance.net_return_1y", 0.91),
            ("operations.aum", 0.89),
        ),
        key_fields=key_fields,
        config=profile_config,
    )

    assert document_type is DocumentType.TEAR_SHEET
    assert key_fields == ("performance.net_return_1y", "operations.aum")
    assert tear_sheet_decision.auto_pass_document is True
    assert tear_sheet_decision.escalate is False

    unknown_key_fields, unknown_config = select_threshold_profile(
        document_type=classify_doc_type("unlabeled manager packet"),
        key_fields=_GLOBAL_KEY_FIELDS,
        config=config,
    )
    unknown_decision = evaluate_thresholds(
        result=_result(
            ("performance.net_return_1y", 0.91),
            ("operations.aum", 0.89),
        ),
        key_fields=unknown_key_fields,
        config=unknown_config,
    )

    assert unknown_key_fields == _GLOBAL_KEY_FIELDS
    assert unknown_decision.escalate is True
    assert unknown_decision.escalation_reason == "missing_mandatory_field:terms.management_fee"
