"""Tests for normalization from multimodal provider output to canonical fields."""

from __future__ import annotations

from inv_man_intake.extraction.providers.base import (
    ExtractedImage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    ProviderExtractionOutput,
    SourceLocation,
)
from inv_man_intake.extraction.providers.normalize import normalize_provider_output


def test_normalize_provider_output_builds_canonical_fields() -> None:
    location = SourceLocation(source_doc_id="doc_1", source_page=2)
    output = ProviderExtractionOutput(
        source_doc_id="doc_1",
        provider_name="dummy-provider",
        text_blocks=(ExtractedTextBlock(text="alpha", location=location),),
        tables=(
            ExtractedTable(
                location=location,
                cells=(
                    ExtractedTableCell(row_index=0, column_index=0, value="A1"),
                    ExtractedTableCell(row_index=1, column_index=0, value="B1", confidence=0.67),
                ),
            ),
        ),
        images=(
            ExtractedImage(
                location=location,
                ocr_text="invoice number",
                description="header image",
            ),
        ),
    )

    result = normalize_provider_output(output)
    by_key = {field.key: field for field in result.fields}

    assert result.source_doc_id == "doc_1"
    assert result.provider_name == "dummy-provider"
    assert by_key["text.block.0"].value == "alpha"
    assert by_key["text.block.0"].confidence == 0.0
    assert by_key["text.block.0"].method == "dummy-provider"
    assert by_key["text.block.0"].location == location
    assert by_key["text.block.0"].snippet == "alpha"
    assert by_key["text.block.0"].snippet_metadata is not None
    assert by_key["text.block.0"].snippet_metadata.kind == "text-block"
    assert by_key["table.0.r0.c0"].value == "A1"
    assert by_key["table.0.r0.c0"].confidence == 0.0
    assert by_key["table.0.r0.c0"].method == "dummy-provider"
    assert by_key["table.0.r0.c0"].location == location
    assert by_key["table.0.r0.c0"].snippet == "A1"
    assert by_key["table.0.r0.c0"].snippet_metadata is not None
    assert by_key["table.0.r0.c0"].snippet_metadata.kind == "table-cell"
    assert by_key["table.0.r1.c0"].confidence == 0.67
    assert by_key["image.0.ocr_text"].value == "invoice number"
    assert by_key["image.0.ocr_text"].method == "dummy-provider"
    assert by_key["image.0.ocr_text"].location == location
    assert by_key["image.0.ocr_text"].snippet == "invoice number"
    assert by_key["image.0.ocr_text"].snippet_metadata is not None
    assert by_key["image.0.ocr_text"].snippet_metadata.kind == "image-ocr"
    assert by_key["image.0.description"].value == "header image"
    assert by_key["image.0.description"].method == "dummy-provider"
    assert by_key["image.0.description"].location == location
    assert by_key["image.0.description"].snippet == "header image"
    assert by_key["image.0.description"].snippet_metadata is not None
    assert by_key["image.0.description"].snippet_metadata.kind == "image-description"

    for field in result.fields:
        assert field.source_doc_id == "doc_1"
        assert field.source_page == 2


def test_normalize_provider_output_uses_placeholders_for_missing_metadata() -> None:
    output = ProviderExtractionOutput(
        source_doc_id="doc_2",
        provider_name="dummy-provider",
        text_blocks=(
            ExtractedTextBlock(
                text="alpha",
                location=SourceLocation(source_doc_id="doc_2", source_page=None),
            ),
        ),
        tables=(
            ExtractedTable(
                location=None,
                cells=(ExtractedTableCell(row_index=0, column_index=1, value="A2"),),
            ),
        ),
        images=(
            ExtractedImage(
                location=SourceLocation(source_doc_id="doc_2", source_page=None),
                ocr_text="ocr value",
            ),
        ),
    )

    result = normalize_provider_output(output)

    assert len(result.fields) == 3
    for field in result.fields:
        assert field.source_doc_id == "doc_2"
        assert field.source_page == 0
        assert field.confidence == 0.0
