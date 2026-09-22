"""Optional Doc-Lineage PDF extraction behind the existing intake provider port."""

from __future__ import annotations

import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    SourceLocation,
    validate_extracted_document_result,
)
from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider

_FIELD_LABELS = (
    "manager",
    "strategy asset class",
    "management fee",
    "performance fee",
    "net return 1y",
    "aum",
    "key person risk",
    "strategy",
    "benchmark",
)
_FIELD_BOUNDARY = re.compile(
    r"\s+(?=(?:" + "|".join(re.escape(label) for label in _FIELD_LABELS) + r")\s*[:\-])",
    re.IGNORECASE,
)


class IncompleteExtractionError(RuntimeError):
    """A PDF has unreadable pages; preserve counts and readable partial output."""

    def __init__(self, *, coverage: Any, partial_result: ExtractedDocumentResult) -> None:
        self.coverage = coverage
        self.partial_result = partial_result
        super().__init__(
            "Doc-Lineage left unreadable PDF pages "
            f"(text_layer={coverage.pages_with_text_layer}, "
            f"recognized={coverage.pages_recognized}, "
            f"unreadable={coverage.pages_unreadable})"
        )


class DocLineageExtractionProvider:
    """Map Doc-Lineage spans to canonical intake fields without losing page provenance."""

    def __init__(
        self,
        *,
        extractor: Callable[..., Any] | None = None,
        cache_factory: Callable[[], Any] | None = None,
    ) -> None:
        if extractor is None or cache_factory is None:
            from doc_lineage.extract import ExtractCache, extract

            extractor = extractor or extract
            cache_factory = cache_factory or ExtractCache
        self._extractor = extractor
        self._cache_factory = cache_factory
        self._field_extractor = PrimaryRegexExtractionProvider()

    @property
    def name(self) -> str:
        return "doc-lineage"

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        """Extract PDF bytes; never persist source bytes or extracted text to a home cache."""
        with tempfile.TemporaryDirectory(prefix="imi-doc-lineage-") as directory:
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".pdf", delete=False) as stream:
                stream.write(content)
                path = Path(stream.name)
            document = self._extractor(path, ocr_enabled=True, cache=self._cache_factory())

        fields: list[ExtractedField] = []
        seen_keys: set[str] = set()
        for span in document.spans:
            if not isinstance(span.page, int) or isinstance(span.page, bool) or span.page < 1:
                raise ValueError("Doc-Lineage returned an invalid PDF page pointer")
        for span in sorted(document.spans, key=lambda item: item.page):
            location = SourceLocation(
                source_doc_id=source_doc_id,
                source_page=span.page,
                bbox=span.bbox,
            )
            # Upstream normalizes a page into one line. Restore boundaries before
            # the existing field parser so free-text values stop at the next label.
            delimited = _FIELD_BOUNDARY.sub("\n", span.text)
            parsed = self._field_extractor.extract(source_doc_id, delimited.encode("utf-8"))
            for field in parsed.fields:
                if field.key in seen_keys:
                    continue
                seen_keys.add(field.key)
                fields.append(
                    ExtractedField(
                        key=field.key,
                        value=field.value,
                        confidence=field.confidence,
                        source_doc_id=source_doc_id,
                        source_page=span.page,
                        method=f"{self.name}:{span.source}",
                        location=location,
                        snippet=field.snippet,
                        snippet_metadata=field.snippet_metadata,
                    )
                )

        result = ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            provider_name=self.name,
            fields=tuple(fields),
        )
        validate_extracted_document_result(result)
        if document.coverage.pages_unreadable:
            raise IncompleteExtractionError(coverage=document.coverage, partial_result=result)
        return result


__all__ = ["DocLineageExtractionProvider", "IncompleteExtractionError"]
