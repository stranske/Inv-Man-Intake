"""Normalization utilities for provider modality outputs."""

from __future__ import annotations

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
)

_UNKNOWN_CONFIDENCE = 0.0
_UNKNOWN_SOURCE_PAGE = 0


def normalize_provider_output(output: ProviderExtractionOutput) -> ExtractedDocumentResult:
    """Convert multimodal provider output into canonical extracted fields."""

    fields: list[ExtractedField] = []
    fields.extend(
        _normalize_text_blocks(output.provider_name, output.source_doc_id, output.text_blocks)
    )
    fields.extend(_normalize_tables(output.provider_name, output.source_doc_id, output.tables))
    fields.extend(_normalize_images(output.provider_name, output.source_doc_id, output.images))

    return ExtractedDocumentResult(
        source_doc_id=output.source_doc_id,
        fields=tuple(fields),
        provider_name=output.provider_name,
    )


def _normalize_text_blocks(
    provider_name: str,
    source_doc_id: str,
    text_blocks: tuple[ExtractedTextBlock, ...],
) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for index, block in enumerate(text_blocks):
        fields.append(
            ExtractedField(
                key=f"text.block.{index}",
                value=block.text,
                confidence=_UNKNOWN_CONFIDENCE,
                source_doc_id=source_doc_id,
                source_page=block.location.source_page or _UNKNOWN_SOURCE_PAGE,
                method=provider_name,
                location=block.location,
                snippet=block.text,
                snippet_metadata=SnippetMetadata(kind="text-block"),
            )
        )
    return fields


def _normalize_tables(
    provider_name: str, source_doc_id: str, tables: tuple[ExtractedTable, ...]
) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for table_index, table in enumerate(tables):
        source_page = (
            table.location.source_page
            if table.location and table.location.source_page is not None
            else _UNKNOWN_SOURCE_PAGE
        )
        for cell in table.cells:
            fields.append(
                _table_cell_to_field(
                    source_doc_id=source_doc_id,
                    table_index=table_index,
                    cell=cell,
                    source_page=source_page,
                    provider_name=provider_name,
                    location=table.location,
                )
            )
    return fields


def _table_cell_to_field(
    source_doc_id: str,
    table_index: int,
    cell: ExtractedTableCell,
    source_page: int,
    provider_name: str,
    location: SourceLocation | None,
) -> ExtractedField:
    return ExtractedField(
        key=f"table.{table_index}.r{cell.row_index}.c{cell.column_index}",
        value=cell.value,
        confidence=(cell.confidence if cell.confidence is not None else _UNKNOWN_CONFIDENCE),
        source_doc_id=source_doc_id,
        source_page=source_page,
        method=provider_name,
        location=location,
        snippet=cell.value,
        snippet_metadata=SnippetMetadata(kind="table-cell"),
    )


def _normalize_images(
    provider_name: str, source_doc_id: str, images: tuple[ExtractedImage, ...]
) -> list[ExtractedField]:
    fields: list[ExtractedField] = []
    for index, image in enumerate(images):
        source_page = image.location.source_page or _UNKNOWN_SOURCE_PAGE
        if image.ocr_text:
            fields.append(
                ExtractedField(
                    key=f"image.{index}.ocr_text",
                    value=image.ocr_text,
                    confidence=_UNKNOWN_CONFIDENCE,
                    source_doc_id=source_doc_id,
                    source_page=source_page,
                    method=provider_name,
                    location=image.location,
                    snippet=image.ocr_text,
                    snippet_metadata=SnippetMetadata(kind="image-ocr"),
                )
            )
        if image.description:
            fields.append(
                ExtractedField(
                    key=f"image.{index}.description",
                    value=image.description,
                    confidence=_UNKNOWN_CONFIDENCE,
                    source_doc_id=source_doc_id,
                    source_page=source_page,
                    method=provider_name,
                    location=image.location,
                    snippet=image.description,
                    snippet_metadata=SnippetMetadata(kind="image-description"),
                )
            )
    return fields
