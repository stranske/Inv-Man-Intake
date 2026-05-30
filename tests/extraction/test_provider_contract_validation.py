"""Validation tests for extraction provider contract helpers."""

from __future__ import annotations

import pytest

from inv_man_intake.extraction.confidence import ThresholdDecision, attach_threshold_summary
from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    ExtractedImage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    ProviderExtractionOutput,
    SnippetMetadata,
    SourceLocation,
    validate_extracted_document_result,
    validate_provider_output,
)


def test_validate_provider_output_accepts_valid_payload() -> None:
    output = ProviderExtractionOutput(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        text_blocks=(
            ExtractedTextBlock(
                text="alpha",
                location=SourceLocation(source_doc_id="doc_1", source_page=1),
            ),
        ),
        tables=(
            ExtractedTable(
                cells=(
                    ExtractedTableCell(row_index=0, column_index=0, value="A1"),
                    ExtractedTableCell(row_index=1, column_index=0, value="B1", confidence=0.9),
                ),
                location=SourceLocation(source_doc_id="doc_1", source_page=2),
            ),
        ),
        images=(
            ExtractedImage(
                location=SourceLocation(source_doc_id="doc_1", source_page=3),
                ocr_text="invoice id",
            ),
        ),
    )

    validate_provider_output(output)


def test_validate_provider_output_rejects_cross_document_source_location() -> None:
    output = ProviderExtractionOutput(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        text_blocks=(
            ExtractedTextBlock(
                text="alpha",
                location=SourceLocation(source_doc_id="doc_2", source_page=1),
            ),
        ),
    )

    with pytest.raises(ValueError, match="must match provider output"):
        validate_provider_output(output)


def test_validate_extracted_document_result_accepts_valid_payload() -> None:
    result = ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        fields=(
            ExtractedField(
                key="terms.management_fee",
                value="2%",
                confidence=0.86,
                source_doc_id="doc_1",
                source_page=1,
                method="fallback-adapter",
            ),
        ),
    )

    validate_extracted_document_result(result)


def test_validate_extracted_document_result_rejects_empty_method() -> None:
    result = ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        fields=(
            ExtractedField(
                key="terms.management_fee",
                value="2%",
                confidence=0.86,
                source_doc_id="doc_1",
                source_page=1,
                method="",
            ),
        ),
    )

    with pytest.raises(ValueError, match="method"):
        validate_extracted_document_result(result)


def test_validate_extracted_document_result_accepts_structured_field_location() -> None:
    location = SourceLocation(
        source_doc_id="doc_1",
        source_page=1,
        bbox=(0.0, 1.0, 2.0, 3.0),
        table_index=2,
    )
    result = ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        fields=(
            ExtractedField(
                key="terms.management_fee",
                value="2%",
                confidence=0.86,
                source_doc_id="doc_1",
                source_page=1,
                method="fallback-adapter",
                location=location,
                snippet="Management fee: 2%",
                snippet_metadata=SnippetMetadata(kind="regex-match", char_start=0, char_end=18),
            ),
        ),
    )

    validate_extracted_document_result(result)
    assert result.fields[0].location == location
    assert result.fields[0].snippet == "Management fee: 2%"
    assert result.fields[0].snippet_metadata == SnippetMetadata(
        kind="regex-match",
        char_start=0,
        char_end=18,
    )


def test_validate_extracted_document_result_rejects_cross_document_field_location() -> None:
    result = ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        fields=(
            ExtractedField(
                key="terms.management_fee",
                value="2%",
                confidence=0.86,
                source_doc_id="doc_1",
                source_page=1,
                method="fallback-adapter",
                location=SourceLocation(source_doc_id="doc_2", source_page=1),
            ),
        ),
    )

    with pytest.raises(ValueError, match="must match provider output"):
        validate_extracted_document_result(result)


def test_validate_extracted_document_result_rejects_negative_field_location_page() -> None:
    result = ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        fields=(
            ExtractedField(
                key="terms.management_fee",
                value="2%",
                confidence=0.86,
                source_doc_id="doc_1",
                source_page=1,
                method="fallback-adapter",
                location=SourceLocation(source_doc_id="doc_1", source_page=-1),
            ),
        ),
    )

    with pytest.raises(ValueError, match="source_page"):
        validate_extracted_document_result(result)


def test_structured_field_location_round_trips_through_threshold_summary() -> None:
    location = SourceLocation(
        source_doc_id="doc_1",
        source_page=1,
        bbox=(0.0, 1.0, 2.0, 3.0),
        table_index=2,
    )
    result = ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        fields=(
            ExtractedField(
                key="terms.management_fee",
                value="2%",
                confidence=0.86,
                source_doc_id="doc_1",
                source_page=1,
                method="fallback-adapter",
                location=location,
                snippet="Management fee: 2%",
                snippet_metadata=SnippetMetadata(kind="regex-match", char_start=0, char_end=18),
            ),
        ),
    )
    decision = ThresholdDecision(
        auto_accept_fields=("terms.management_fee",),
        key_field_coverage_ratio=1.0,
        auto_pass_document=True,
        escalate=False,
        escalation_reason=None,
    )

    with_summary = attach_threshold_summary(result=result, decision=decision)

    assert with_summary.fields[0].location == location
    assert with_summary.fields[0].snippet == "Management fee: 2%"
    assert with_summary.fields[0].snippet_metadata == SnippetMetadata(
        kind="regex-match",
        char_start=0,
        char_end=18,
    )
    assert {field.method for field in with_summary.fields} == {
        "fallback-adapter",
        "threshold-summary",
    }
    validate_extracted_document_result(with_summary)


def test_validate_extracted_document_result_rejects_invalid_confidence() -> None:
    result = ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        fields=(
            ExtractedField(
                key="terms.management_fee",
                value="2%",
                confidence=1.2,
                source_doc_id="doc_1",
                source_page=1,
                method="fallback-adapter",
            ),
        ),
    )

    with pytest.raises(ValueError, match="confidence"):
        validate_extracted_document_result(result)


def test_validate_extracted_document_result_rejects_invalid_snippet_metadata() -> None:
    result = ExtractedDocumentResult(
        source_doc_id="doc_1",
        provider_name="fallback-adapter",
        fields=(
            ExtractedField(
                key="terms.management_fee",
                value="2%",
                confidence=0.86,
                source_doc_id="doc_1",
                source_page=1,
                method="fallback-adapter",
                snippet_metadata=SnippetMetadata(kind="regex-match", char_start=8, char_end=2),
            ),
        ),
    )

    with pytest.raises(ValueError, match="char_end"):
        validate_extracted_document_result(result)
