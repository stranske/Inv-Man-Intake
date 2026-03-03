"""Validation tests for extraction provider contract helpers."""

from __future__ import annotations

import pytest

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    ExtractedImage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    ProviderExtractionOutput,
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
            ),
        ),
    )

    validate_extracted_document_result(result)


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
            ),
        ),
    )

    with pytest.raises(ValueError, match="confidence"):
        validate_extracted_document_result(result)
