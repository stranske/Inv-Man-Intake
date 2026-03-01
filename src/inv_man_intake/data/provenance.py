"""Field provenance and correction history value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedFieldRecord:
    """Extracted field value with source-document provenance metadata."""

    field_id: str
    document_id: str
    field_key: str
    value: str
    confidence: float
    source_page: int
    source_snippet: str | None
    extracted_at: str


@dataclass(frozen=True)
class CorrectionRecord:
    """Append-only correction entry for an extracted field."""

    correction_id: int
    field_id: str
    corrected_value: str
    reason: str | None
    corrected_by: str | None
    corrected_at: str
