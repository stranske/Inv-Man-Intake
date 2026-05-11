"""Image extraction, classification helpers, and data models."""

from inv_man_intake.images.classifier import (
    VisualArtifactClassification,
    VisualClassificationLabel,
    classify_visual_artifact,
)
from inv_man_intake.images.extractor import UnsupportedVisualSourceError, extract_visual_artifacts
from inv_man_intake.images.models import ArtifactSource, VisualArtifact

__all__ = [
    "ArtifactSource",
    "UnsupportedVisualSourceError",
    "VisualArtifactClassification",
    "VisualClassificationLabel",
    "VisualArtifact",
    "classify_visual_artifact",
    "extract_visual_artifacts",
]
