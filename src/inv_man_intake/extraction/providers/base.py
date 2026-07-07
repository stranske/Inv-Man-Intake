"""Canonical extraction provider interface and output contract.

This module intentionally preserves Inv-Man-Intake's historical import paths
while delegating the shared provider contract to ``stranske-pdf-extract``.
"""

from __future__ import annotations

try:
    from stranske_pdf_extract.contract import (
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
    from stranske_pdf_extract.provider import ExtractionProvider, MultiModalExtractionProvider
except ModuleNotFoundError as exc:  # pragma: no cover - exercised in the Pyodide browser bundle.
    if exc.name and not exc.name.startswith("stranske_pdf_extract"):
        raise

    from dataclasses import dataclass
    from typing import Any, Protocol

    @dataclass(frozen=True)
    class SourceLocation:  # type: ignore[no-redef]
        source_doc_id: str
        source_page: int | None = None
        bbox: tuple[float, float, float, float] | None = None
        table_index: int | None = None

    @dataclass(frozen=True)
    class SnippetMetadata:  # type: ignore[no-redef]
        kind: str
        char_start: int | None = None
        char_end: int | None = None

    @dataclass(frozen=True)
    class ExtractedField:  # type: ignore[no-redef]
        key: str
        value: str
        confidence: float
        source_doc_id: str
        source_page: int
        method: str
        location: SourceLocation | None = None
        snippet: str | None = None
        snippet_metadata: SnippetMetadata | None = None

    @dataclass(frozen=True)
    class ExtractedDocumentResult:  # type: ignore[no-redef]
        source_doc_id: str
        provider_name: str
        fields: tuple[ExtractedField, ...] = ()
        images: tuple[object, ...] = ()
        tables: tuple[object, ...] = ()
        text_blocks: tuple[object, ...] = ()

    @dataclass(frozen=True)
    class ExtractedImage:  # type: ignore[no-redef]
        image_id: str = ""
        location: SourceLocation | None = None
        ocr_text: str = ""
        description: str = ""
        content: bytes = b""

    @dataclass(frozen=True)
    class ExtractedTable:  # type: ignore[no-redef]
        table_id: str = ""
        location: SourceLocation | None = None
        cells: tuple[ExtractedTableCell, ...] = ()

    @dataclass(frozen=True)
    class ExtractedTableCell:  # type: ignore[no-redef]
        row_index: int
        column_index: int
        value: str
        confidence: float | None = None

    @dataclass(frozen=True)
    class ExtractedTextBlock:  # type: ignore[no-redef]
        text: str
        location: SourceLocation

    @dataclass(frozen=True)
    class ProviderExtractionOutput:  # type: ignore[no-redef]
        source_doc_id: str
        provider_name: str
        text_blocks: tuple[ExtractedTextBlock, ...] = ()
        tables: tuple[ExtractedTable, ...] = ()
        images: tuple[ExtractedImage, ...] = ()

    class ExtractionProvider(Protocol):  # type: ignore[no-redef]
        def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult: ...

    class MultiModalExtractionProvider(ExtractionProvider, Protocol):  # type: ignore[no-redef,misc]
        pass

    def validate_extracted_document_result(result: ExtractedDocumentResult) -> None:
        for field_item in result.fields:
            if field_item.source_doc_id != result.source_doc_id:
                raise ValueError("source_doc_id must match output")
            if not field_item.method:
                raise ValueError("method must be non-empty")
            if not 0.0 <= field_item.confidence <= 1.0:
                raise ValueError("confidence must be between 0 and 1")
            if field_item.location is not None:
                _validate_location(field_item.location, result.source_doc_id)
            if field_item.snippet_metadata is not None:
                _validate_snippet_metadata(field_item.snippet_metadata)

    def validate_provider_output(output: Any) -> None:
        for block in getattr(output, "text_blocks", ()):
            _validate_location(block.location, output.source_doc_id)
        for table in getattr(output, "tables", ()):
            if table.location is not None:
                _validate_location(table.location, output.source_doc_id)
            for cell in table.cells:
                if cell.confidence is not None and not 0.0 <= cell.confidence <= 1.0:
                    raise ValueError("confidence must be between 0 and 1")
        for image in getattr(output, "images", ()):
            if image.location is not None:
                _validate_location(image.location, output.source_doc_id)

    def _validate_location(location: SourceLocation, source_doc_id: str) -> None:
        if location.source_doc_id != source_doc_id:
            raise ValueError("source_doc_id must match output")
        if location.source_page is not None and location.source_page < 0:
            raise ValueError("source_page must be non-negative")

    def _validate_snippet_metadata(metadata: SnippetMetadata) -> None:
        if not metadata.kind:
            raise ValueError("snippet metadata kind must be non-empty")
        if metadata.char_start is not None and metadata.char_start < 0:
            raise ValueError("char_start must be non-negative")
        if metadata.char_end is not None and metadata.char_end < 0:
            raise ValueError("char_end must be non-negative")
        if (
            metadata.char_start is not None
            and metadata.char_end is not None
            and metadata.char_end < metadata.char_start
        ):
            raise ValueError("char_end must be greater than or equal to char_start")


__all__ = [
    "ExtractedDocumentResult",
    "ExtractedField",
    "ExtractedImage",
    "ExtractedTable",
    "ExtractedTableCell",
    "ExtractedTextBlock",
    "ExtractionProvider",
    "MultiModalExtractionProvider",
    "ProviderExtractionOutput",
    "SnippetMetadata",
    "SourceLocation",
    "validate_extracted_document_result",
    "validate_provider_output",
]
