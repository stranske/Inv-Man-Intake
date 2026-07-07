"""Tests for document-type-specific extraction threshold profiles."""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.extraction.confidence import (
    evaluate_thresholds,
    load_threshold_config,
    select_threshold_profile,
)
from inv_man_intake.extraction.doc_type import DocumentType, classify_doc_type
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.intake.standard_elements import load_standard_element_library

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


def test_classifier_handles_specific_document_types_without_ambiguous_matches() -> None:
    assert classify_doc_type("Completed due diligence questionnaire") is DocumentType.DDQ
    assert classify_doc_type("Factsheet with month-end returns and AUM") is DocumentType.TEAR_SHEET
    assert classify_doc_type("Monthly commentary for investors") is DocumentType.MONTHLY_LETTER
    assert classify_doc_type("Private placement memorandum for Fund VI") is DocumentType.PITCHBOOK
    assert classify_doc_type("ESG parts per million emissions appendix") is DocumentType.UNKNOWN


def test_classifier_consumes_standard_library_doc_types_from_data() -> None:
    library = load_standard_element_library(
        {
            "version": "test",
            "non_authoritative": True,
            "doc_types": {
                "capital_call_notice": [
                    {
                        "key": "operations.capital_call_due_date",
                        "detector_name": "field_present",
                        "mandatory": True,
                    }
                ],
                "custom_pitchbook": [
                    {
                        "key": "operations.aum",
                        "detector_name": "field_present",
                        "mandatory": True,
                    }
                ],
            },
        }
    )

    assert (
        classify_doc_type("Fund VI custom pitchbook with AUM", standard_library=library)
        is DocumentType.PITCHBOOK
    )
    assert (
        classify_doc_type("Capital call notice for Fund VI", standard_library=library)
        is DocumentType.UNKNOWN
    )

    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path(__file__).resolve().parents[2] / "src" / "inv_man_intake").rglob("*.py")
    )
    assert "capital_call_notice" not in source_text
    assert "operations.capital_call_due_date" not in source_text


def test_profile_overrides_are_merged_for_each_document_type() -> None:
    config = load_threshold_config(_CONFIG_PATH)

    monthly_fields, monthly_config = select_threshold_profile(
        document_type=DocumentType.MONTHLY_LETTER,
        key_fields=_GLOBAL_KEY_FIELDS,
        config=config,
    )
    monthly_decision = evaluate_thresholds(
        result=_result(("performance.net_return_1y", 0.91)),
        key_fields=monthly_fields,
        config=monthly_config,
    )
    assert monthly_fields == ("performance.net_return_1y", "commentary.market_update")
    assert monthly_config.document_key_field_coverage_min == 0.5
    assert monthly_decision.auto_pass_document is True
    assert monthly_decision.escalate is False

    ddq_fields, ddq_config = select_threshold_profile(
        document_type=DocumentType.DDQ,
        key_fields=_GLOBAL_KEY_FIELDS,
        config=config,
    )
    ddq_decision = evaluate_thresholds(
        result=_result(("terms.management_fee", 0.91), ("operations.aum", 0.89)),
        key_fields=ddq_fields,
        config=ddq_config,
    )
    assert ddq_fields == (
        "terms.management_fee",
        "operations.aum",
        "operations.inception_date",
    )
    assert ddq_decision.escalate is True
    assert ddq_decision.escalation_reason == "low_key_field_coverage"

    pitchbook_fields, pitchbook_config = select_threshold_profile(
        document_type=DocumentType.PITCHBOOK,
        key_fields=_GLOBAL_KEY_FIELDS,
        config=config,
    )
    pitchbook_decision = evaluate_thresholds(
        result=_result(
            ("terms.management_fee", 0.91),
            ("performance.net_return_1y", 0.90),
            ("operations.aum", 0.89),
        ),
        key_fields=pitchbook_fields,
        config=pitchbook_config,
    )
    assert pitchbook_fields == _GLOBAL_KEY_FIELDS
    assert pitchbook_decision.escalate is False


def test_profile_without_mandatory_fields_inherits_global_policy(tmp_path: Path) -> None:
    config_path = tmp_path / "thresholds.yaml"
    config_path.write_text(
        """
field_auto_accept_min: 0.85
key_field_confidence_min: 0.75
document_key_field_coverage_min: 0.80
mandatory_field_min: 0.60
mandatory_fields:
  - terms.management_fee
document_profiles:
  tear_sheet:
    key_fields:
      - performance.net_return_1y
    document_key_field_coverage_min: 1.0
""".strip(),
        encoding="utf-8",
    )

    config = load_threshold_config(config_path)
    key_fields, profile_config = select_threshold_profile(
        document_type=DocumentType.TEAR_SHEET,
        key_fields=_GLOBAL_KEY_FIELDS,
        config=config,
    )
    decision = evaluate_thresholds(
        result=_result(("performance.net_return_1y", 0.91)),
        key_fields=key_fields,
        config=profile_config,
    )

    assert profile_config.mandatory_fields == ("terms.management_fee",)
    assert decision.escalate is True
    assert decision.escalation_reason == "missing_mandatory_field:terms.management_fee"


@pytest.mark.parametrize(
    ("config_body", "error"),
    (
        (
            """
field_auto_accept_min: 0.85
key_field_confidence_min: 0.75
document_key_field_coverage_min: 0.80
mandatory_field_min: 0.60
mandatory_fields:
  - terms.management_fee
document_profiles:
  tear_sheet:
    key_fields:
      - performance.net_return_1y
    malformed_profile_line
""",
            "unexpected line in document profile tear_sheet",
        ),
        (
            """
field_auto_accept_min: 0.85
key_field_confidence_min: 0.75
document_key_field_coverage_min: 0.80
mandatory_field_min: 0.60
mandatory_fields:
  - terms.management_fee
document_profiles:
  tear_sheet:
    key_fields:
      performance.net_return_1y
""",
            "unexpected indentation in document_profiles",
        ),
        (
            """
field_auto_accept_min: 0.85
key_field_confidence_min: 0.75
document_key_field_coverage_min: 0.80
mandatory_field_min: 0.60
mandatory_fields:
  - terms.management_fee
document_profiles:
   tear_sheet:
    key_fields:
      - performance.net_return_1y
""",
            "unexpected indentation in document_profiles",
        ),
    ),
)
def test_document_profile_parser_fails_closed(tmp_path: Path, config_body: str, error: str) -> None:
    config_path = tmp_path / "thresholds.yaml"
    config_path.write_text(config_body.strip(), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        load_threshold_config(config_path)
