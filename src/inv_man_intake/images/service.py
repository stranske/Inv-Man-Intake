"""Service helpers for classifying extracted visual artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from inv_man_intake.images.classifier import (
    VisualArtifactClassification,
    classify_visual_artifact,
)
from inv_man_intake.images.extractor import extract_visual_artifacts
from inv_man_intake.images.models import VisualArtifact


@dataclass(frozen=True)
class ClassifiedVisualArtifact:
    """Visual artifact paired with its classification output."""

    artifact: VisualArtifact
    classification: VisualArtifactClassification


def classify_visual_artifacts(
    artifacts: tuple[VisualArtifact, ...],
) -> tuple[ClassifiedVisualArtifact, ...]:
    """Classify each artifact in input order with deterministic reason output."""

    return tuple(
        ClassifiedVisualArtifact(
            artifact=artifact,
            classification=classify_visual_artifact(artifact),
        )
        for artifact in artifacts
    )


def extract_and_classify_visual_artifacts(
    *,
    source_doc_id: str,
    file_name: str,
    content: bytes,
) -> tuple[ClassifiedVisualArtifact, ...]:
    """Extract visual artifacts from a document and classify each result."""

    artifacts = extract_visual_artifacts(
        source_doc_id=source_doc_id,
        file_name=file_name,
        content=content,
    )
    return classify_visual_artifacts(artifacts)
