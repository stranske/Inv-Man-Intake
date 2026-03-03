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
)

_UNKNOWN_CONFIDENCE = 0.0
_UNKNOWN_SOURCE_PAGE = 0


def normalize_provider_output(output: ProviderExtractionOutput) -> ExtractedDocumentResult:
    """Convert multimodal provider output into canonical extracted fields."""

    fields: list[ExtractedField] = []
    fields.extend(_normalize_text_blocks(output.source_doc_id, output.text_blocks))
    fields.extend(_normalize_tables(output.source_doc_id, output.tables))
    fields.extend(_normalize_images(output.source_doc_id, output.images))

    return ExtractedDocumentResult(
        source_doc_id=output.source_doc_id,
        fields=tuple(fields),
        provider_name=output.provider_name,
    )


def _normalize_text_blocks(
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
            )
        )
    return fields


def _normalize_tables(
    source_doc_id: str, tables: tuple[ExtractedTable, ...]
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
                )
            )
    return fields


def _table_cell_to_field(
    source_doc_id: str,
    table_index: int,
    cell: ExtractedTableCell,
    source_page: int,
) -> ExtractedField:
    return ExtractedField(
        key=f"table.{table_index}.r{cell.row_index}.c{cell.column_index}",
        value=cell.value,
        confidence=(cell.confidence if cell.confidence is not None else _UNKNOWN_CONFIDENCE),
        source_doc_id=source_doc_id,
        source_page=source_page,
    )


def _normalize_images(
    source_doc_id: str, images: tuple[ExtractedImage, ...]
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
                )
            )
    return fields
