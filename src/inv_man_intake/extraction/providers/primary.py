"""Primary extraction provider implementation (regex/text heuristic baseline)."""

from __future__ import annotations

import re

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    SnippetMetadata,
    SourceLocation,
)


class PrimaryRegexExtractionProvider:
    """Primary provider that extracts baseline fields from decoded text."""

    _PATTERNS: tuple[tuple[str, str], ...] = (
        ("manager.name", r"manager\s*[:\-]?\s*([A-Za-z0-9 &/\-]+)"),
        ("strategy.asset_class", r"strategy asset class\s*[:\-]?\s*([^;\n]+)"),
        ("terms.management_fee", r"management fee\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?%)"),
        ("terms.performance_fee", r"performance fee\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?%)"),
        ("performance.net_return_1y", r"net return 1y\s*[:\-]?\s*([0-9.-]+%)"),
        ("operations.aum", r"aum\s*[:\-]?\s*([$A-Za-z0-9.]+)"),
        ("team.key_person_risk", r"key person risk\s*[:\-]?\s*([^;\n]+)"),
        ("strategy.name", r"strategy\s*[:\-]?\s*([A-Za-z0-9 /\-]+)"),
        ("benchmark.name", r"benchmark\s*[:\-]?\s*([A-Za-z0-9 &\-/]+)"),
    )

    @property
    def name(self) -> str:
        return "primary-regex"

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        decoded = content.decode("utf-8", errors="ignore")

        fields: list[ExtractedField] = []
        for key, pattern in self._PATTERNS:
            match = re.search(pattern, decoded, flags=re.IGNORECASE)
            if not match:
                continue
            raw_value = match.group(1).strip()
            fields.append(
                ExtractedField(
                    key=key,
                    value=raw_value,
                    confidence=0.82,
                    source_doc_id=source_doc_id,
                    source_page=1,
                    method=self.name,
                    location=SourceLocation(source_doc_id=source_doc_id, source_page=1),
                    snippet=match.group(0).strip(),
                    snippet_metadata=SnippetMetadata(
                        kind="regex-match",
                        char_start=match.start(),
                        char_end=match.end(),
                    ),
                )
            )

        return ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            fields=tuple(fields),
            provider_name=self.name,
        )
