"""Canonical extraction provider interface and output contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ExtractedField:
    """One extracted field with confidence and source location metadata."""

    key: str
    value: str
    confidence: float
    source_doc_id: str
    source_page: int


@dataclass(frozen=True)
class SourceLocation:
    """Location metadata shared across text/table/image extraction outputs."""

    source_doc_id: str
    source_page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    table_index: int | None = None
    image_index: int | None = None


@dataclass(frozen=True)
class ExtractedTextBlock:
    """Text content extracted from the document."""

    text: str
    location: SourceLocation


@dataclass(frozen=True)
class ExtractedTableCell:
    """A single extracted table cell."""

    row_index: int
    column_index: int
    value: str
    confidence: float | None = None


@dataclass(frozen=True)
class ExtractedTable:
    """Tabular extraction payload."""

    cells: tuple[ExtractedTableCell, ...]
    location: SourceLocation | None = None
    table_id: str | None = None


@dataclass(frozen=True)
class ExtractedImage:
    """Image extraction payload, including optional OCR/description text."""

    location: SourceLocation
    image_id: str | None = None
    mime_type: str | None = None
    ocr_text: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ProviderExtractionOutput:
    """Raw extraction output grouped by modality."""

    source_doc_id: str
    provider_name: str
    text_blocks: tuple[ExtractedTextBlock, ...] = ()
    tables: tuple[ExtractedTable, ...] = ()
    images: tuple[ExtractedImage, ...] = ()


@dataclass(frozen=True)
class ExtractedDocumentResult:
    """Canonical result emitted by extraction providers."""

    source_doc_id: str
    fields: tuple[ExtractedField, ...]
    provider_name: str


def validate_provider_output(output: ProviderExtractionOutput) -> None:
    """Validate raw multimodal output emitted by an extraction provider."""

    if not output.source_doc_id:
        raise ValueError("ProviderExtractionOutput.source_doc_id must be non-empty")
    if not output.provider_name:
        raise ValueError("ProviderExtractionOutput.provider_name must be non-empty")

    for block in output.text_blocks:
        _validate_source_location(
            block.location,
            expected_source_doc_id=output.source_doc_id,
            context="text_blocks",
        )

    for table in output.tables:
        if table.location is not None:
            _validate_source_location(
                table.location,
                expected_source_doc_id=output.source_doc_id,
                context="tables",
            )
        for cell in table.cells:
            if cell.confidence is not None and not 0.0 <= cell.confidence <= 1.0:
                raise ValueError("ExtractedTableCell.confidence must be within [0.0, 1.0]")

    for image in output.images:
        _validate_source_location(
            image.location,
            expected_source_doc_id=output.source_doc_id,
            context="images",
        )


def validate_extracted_document_result(result: ExtractedDocumentResult) -> None:
    """Validate canonical extraction output used by orchestration."""

    if not result.source_doc_id:
        raise ValueError("ExtractedDocumentResult.source_doc_id must be non-empty")
    if not result.provider_name:
        raise ValueError("ExtractedDocumentResult.provider_name must be non-empty")

    for field in result.fields:
        if not field.key:
            raise ValueError("ExtractedField.key must be non-empty")
        if not field.value:
            raise ValueError("ExtractedField.value must be non-empty")
        if not 0.0 <= field.confidence <= 1.0:
            raise ValueError("ExtractedField.confidence must be within [0.0, 1.0]")
        if field.source_doc_id != result.source_doc_id:
            raise ValueError("ExtractedField.source_doc_id must match ExtractedDocumentResult")
        if field.source_page < 0:
            raise ValueError("ExtractedField.source_page must be >= 0")


def _validate_source_location(
    location: SourceLocation,
    *,
    expected_source_doc_id: str,
    context: str,
) -> None:
    if not location.source_doc_id:
        raise ValueError(f"SourceLocation.source_doc_id must be non-empty for {context}")
    if location.source_doc_id != expected_source_doc_id:
        raise ValueError(f"SourceLocation.source_doc_id must match provider output for {context}")
    if location.source_page is not None and location.source_page < 0:
        raise ValueError("SourceLocation.source_page must be >= 0 when provided")


@runtime_checkable
class ExtractionProvider(Protocol):
    """Provider protocol for all extraction adapters."""

    @property
    def name(self) -> str:
        """Stable provider name used in orchestration logs."""

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        """Extract canonical fields from raw document bytes."""


@runtime_checkable
class MultiModalExtractionProvider(Protocol):
    """Provider protocol that emits text/table/image extraction outputs."""

    @property
    def name(self) -> str:
        """Stable provider name used in orchestration logs."""

    def extract_modalities(self, source_doc_id: str, content: bytes) -> ProviderExtractionOutput:
        """Extract text, table, and image outputs from raw document bytes."""
