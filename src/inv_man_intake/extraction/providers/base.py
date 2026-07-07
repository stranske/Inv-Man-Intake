"""Canonical extraction provider interface and output contract.

This module intentionally preserves Inv-Man-Intake's historical import paths
while delegating the shared provider contract to ``stranske-pdf-extract``.
"""

from __future__ import annotations

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
