"""Domain models for visual artifact extraction outputs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactSource:
    """Coordinates linking a visual artifact back to its source location."""

    source_doc_id: str
    page_number: int | None = None
    slide_number: int | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class VisualArtifact:
    """Extracted visual artifact payload with stable identity metadata."""

    artifact_id: str
    source: ArtifactSource
    mime_type: str
    sha256: str
    byte_size: int
    storage_path: str
    content: bytes
