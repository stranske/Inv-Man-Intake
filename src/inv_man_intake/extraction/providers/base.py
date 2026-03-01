"""Canonical extraction provider interface and output contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExtractedField:
    """One extracted field with confidence and source location metadata."""

    key: str
    value: str
    confidence: float
    source_doc_id: str
    source_page: int


@dataclass(frozen=True)
class ExtractedDocumentResult:
    """Canonical result emitted by extraction providers."""

    source_doc_id: str
    fields: tuple[ExtractedField, ...]
    provider_name: str


class ExtractionProvider(Protocol):
    """Provider protocol for all extraction adapters."""

    @property
    def name(self) -> str:
        """Stable provider name used in orchestration logs."""

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        """Extract canonical fields from raw document bytes."""
