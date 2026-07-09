"""Optional shared Docling-backed extraction provider adapter."""

from __future__ import annotations

from typing import Any, cast

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    ProviderExtractionOutput,
    validate_extracted_document_result,
)
from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider


class MissingDoclingDependencyError(RuntimeError):
    """Raised when the optional Docling extra is not installed."""


def _load_docling_provider_class() -> type[Any]:
    try:
        from stranske_pdf_extract.providers.docling_provider import DoclingProvider
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
        if exc.name and not exc.name.startswith(("docling", "stranske_pdf_extract")):
            raise
        raise MissingDoclingDependencyError(
            "Install inv-man-intake[extraction-docling] to use DoclingPrimaryExtractionProvider"
        ) from exc

    return cast(type[Any], DoclingProvider)


class DoclingPrimaryExtractionProvider:
    """Adapt the shared Docling provider into IMI's field-extraction pipeline."""

    def __init__(self, *, provider: Any | None = None, do_ocr: bool = False) -> None:
        if provider is not None and do_ocr:
            raise ValueError("do_ocr is only supported when using the default DoclingProvider")
        self._provider = (
            provider if provider is not None else _load_docling_provider_class()(do_ocr=do_ocr)
        )
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
        """Extract raw text/table/image modalities using the shared provider."""

        try:
            return self._provider.extract_modalities(source_doc_id=source_doc_id, content=content)
        except Exception as exc:  # pragma: no cover - depends on optional extra
            if exc.__class__.__name__ != "DoclingUnavailableError":
                raise
            raise MissingDoclingDependencyError(
                "Install inv-man-intake[extraction-docling] to use DoclingPrimaryExtractionProvider"
            ) from exc


__all__ = [
    "DoclingPrimaryExtractionProvider",
    "MissingDoclingDependencyError",
]
