"""Optional Docling-backed extraction provider.

Docling stays out of the core dependency set. Import and conversion happen only
when this provider is used, so the browser demo and baseline package install
remain fixture-backed and lightweight.
"""

from __future__ import annotations

import re
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Any

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    ExtractedTextBlock,
    ExtractionProvider,
    MultiModalExtractionProvider,
    ProviderExtractionOutput,
    SourceLocation,
    validate_extracted_document_result,
    validate_provider_output,
)
from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider


class MissingDoclingDependencyError(RuntimeError):
    """Raised when the optional Docling extra is not installed."""


class DoclingPrimaryExtractionProvider:
    """Extract document text via Docling and map it through existing contracts."""

    def __init__(self, *, converter: Any | None = None) -> None:
        self._converter = converter
        self._field_extractor = PrimaryRegexExtractionProvider()

    @property
    def name(self) -> str:
        return "docling-primary"

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        """Extract canonical fields from Docling text output."""

        multimodal = self.extract_modalities(source_doc_id=source_doc_id, content=content)
        markdown = "\n\n".join(block.text for block in multimodal.text_blocks)
        result = self._field_extractor.extract(
            source_doc_id=source_doc_id,
            content=markdown.encode("utf-8"),
        )
        normalized = ExtractedDocumentResult(
            source_doc_id=result.source_doc_id,
            fields=tuple(
                ExtractedField(
                    key=field.key,
                    value=field.value,
                    confidence=field.confidence,
                    source_doc_id=field.source_doc_id,
                    source_page=field.source_page,
                    method=self.name,
                    location=field.location,
                    snippet=field.snippet,
                    snippet_metadata=field.snippet_metadata,
                )
                for field in result.fields
            ),
            provider_name=self.name,
        )
        validate_extracted_document_result(normalized)
        return normalized

    def extract_modalities(self, source_doc_id: str, content: bytes) -> ProviderExtractionOutput:
        """Extract raw text/table/image modalities from document bytes."""

        converter = self._resolve_converter()
        result = self._convert_bytes(
            converter=converter, source_doc_id=source_doc_id, content=content
        )
        text = self._export_text(result)
        output = ProviderExtractionOutput(
            source_doc_id=source_doc_id,
            provider_name=self.name,
            text_blocks=(
                (
                    ExtractedTextBlock(
                        text=text,
                        location=SourceLocation(source_doc_id=source_doc_id, source_page=1),
                    ),
                )
                if text.strip()
                else ()
            ),
        )
        validate_provider_output(output)
        return output

    def _resolve_converter(self) -> Any:
        if self._converter is not None:
            return self._converter
        try:
            converter_module = import_module("docling.document_converter")
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
            raise MissingDoclingDependencyError(
                "Install inv-man-intake[extraction-docling] to use DoclingPrimaryExtractionProvider"
            ) from exc
        document_converter_cls = converter_module.DocumentConverter
        self._converter = document_converter_cls()
        return self._converter

    @staticmethod
    def _convert_bytes(*, converter: Any, source_doc_id: str, content: bytes) -> Any:
        suffix = _suffix_for_source(source_doc_id=source_doc_id, content=content)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        try:
            return converter.convert(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _export_text(result: Any) -> str:
        document = getattr(result, "document", result)
        for method_name in (
            "export_to_markdown",
            "export_to_text",
            "export_to_document_tokens",
        ):
            method = getattr(document, method_name, None)
            if callable(method):
                exported = method()
                if exported is not None:
                    return str(exported)
        return str(document)


def _suffix_for_source(*, source_doc_id: str, content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return ".pdf"
    match = re.search(r"(\.[A-Za-z0-9]{2,8})$", source_doc_id)
    if match:
        return match.group(1)
    return ".bin"


__all__ = [
    "DoclingPrimaryExtractionProvider",
    "MissingDoclingDependencyError",
]


_provider = DoclingPrimaryExtractionProvider()
assert isinstance(_provider, ExtractionProvider)
assert isinstance(_provider, MultiModalExtractionProvider)
