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
