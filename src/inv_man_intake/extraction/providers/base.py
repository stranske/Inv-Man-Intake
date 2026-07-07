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
except ModuleNotFoundError:  # pragma: no cover - exercised in the Pyodide browser bundle.
    from dataclasses import dataclass
    from typing import Any, Protocol

    @dataclass(frozen=True)
    class ExtractedField:
        key: str
        value: str
        confidence: float
        source_doc_id: str
        source_page: int
        method: str

    @dataclass(frozen=True)
    class ExtractedDocumentResult:
        source_doc_id: str
        provider_name: str
        fields: tuple[ExtractedField, ...] = ()
        images: tuple[object, ...] = ()
        tables: tuple[object, ...] = ()
        text_blocks: tuple[object, ...] = ()

    @dataclass(frozen=True)
    class ExtractedImage:
        source_doc_id: str
        page_number: int | None = None
        image_index: int = 0
        content: bytes = b""

    @dataclass(frozen=True)
    class ExtractedTable:
        source_doc_id: str
        page_number: int | None = None
        cells: tuple[object, ...] = ()

    @dataclass(frozen=True)
    class ExtractedTableCell:
        row: int
        column: int
        text: str

    @dataclass(frozen=True)
    class ExtractedTextBlock:
        text: str
        source_page: int | None = None

    @dataclass(frozen=True)
    class ProviderExtractionOutput:
        result: ExtractedDocumentResult

    @dataclass(frozen=True)
    class SnippetMetadata:
        source_doc_id: str
        source_page: int | None = None

    @dataclass(frozen=True)
    class SourceLocation:
        source_doc_id: str
        source_page: int | None = None

    class ExtractionProvider(Protocol):
        def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult: ...

    class MultiModalExtractionProvider(ExtractionProvider, Protocol):
        pass

    def validate_extracted_document_result(result: ExtractedDocumentResult) -> None:
        _ = result

    def validate_provider_output(output: Any) -> None:
        _ = output


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
