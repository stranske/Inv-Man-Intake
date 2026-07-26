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
class ImageGeometry:
    """Decoding geometry carried from a PDF image XObject dictionary.

    Without these keys a ``/FlateDecode`` sample stream cannot be turned back
    into a viewable raster, which is why they are retained rather than dropped
    at extraction time.
    """

    width: int | None = None
    height: int | None = None
    bits_per_component: int | None = None
    color_space: str | None = None
    color_components: int | None = None
    filter_name: str | None = None
    predictor: int | None = None
    predictor_colors: int | None = None
    predictor_columns: int | None = None
    palette: bytes | None = None
    has_smask: bool = False

    @property
    def is_complete(self) -> bool:
        """Whether every field required to rebuild a raster is present."""

        return (
            self.width is not None
            and self.width > 0
            and self.height is not None
            and self.height > 0
            and self.bits_per_component is not None
            and self.color_components is not None
        )


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
    geometry: ImageGeometry | None = None
    unsupported_reason: str | None = None
