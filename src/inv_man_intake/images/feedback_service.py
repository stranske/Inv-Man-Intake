"""Service helpers for visual-artifact feedback capture."""

from __future__ import annotations

from dataclasses import dataclass

from inv_man_intake.contracts.image_feedback_contract import ImageFeedbackRecord
from inv_man_intake.data.provenance import VisualArtifactFeedbackRecord
from inv_man_intake.data.repository import VisualArtifactRepository


@dataclass(frozen=True)
class FeedbackWriteResult:
    """Result returned after a reviewer feedback upsert."""

    record: ImageFeedbackRecord
    replaced_existing: bool


class VisualArtifactFeedbackService:
    """Create, read, and upsert feedback for extracted visual artifacts."""

    def __init__(self, repository: VisualArtifactRepository) -> None:
        self._repository = repository

    def record_feedback(self, record: ImageFeedbackRecord) -> FeedbackWriteResult:
        """Persist feedback, replacing the same reviewer's prior record for the artifact."""

        replaced_existing = (
            self._repository.get_feedback(record.artifact_id, record.reviewer) is not None
        )
        self._repository.upsert_feedback(
            VisualArtifactFeedbackRecord(
                artifact_id=record.artifact_id,
                is_informative=record.is_informative,
                quality_rank=record.quality_rank,
                reviewer=record.reviewer,
                timestamp=record.timestamp,
                notes=record.notes,
            )
        )
        return FeedbackWriteResult(record=record, replaced_existing=replaced_existing)

    def get_feedback(self, artifact_id: str, reviewer: str) -> ImageFeedbackRecord | None:
        """Return one reviewer's feedback for an artifact when present."""

        record = self._repository.get_feedback(artifact_id, reviewer)
        if record is None:
            return None
        return _to_contract_record(record)

    def list_feedback(self, artifact_id: str) -> tuple[ImageFeedbackRecord, ...]:
        """Return all feedback for an artifact in review-time order."""

        return tuple(
            _to_contract_record(record) for record in self._repository.list_feedback(artifact_id)
        )


def _to_contract_record(record: VisualArtifactFeedbackRecord) -> ImageFeedbackRecord:
    return ImageFeedbackRecord(
        artifact_id=record.artifact_id,
        is_informative=record.is_informative,
        quality_rank=record.quality_rank,
        reviewer=record.reviewer,
        timestamp=record.timestamp,
        notes=record.notes,
    )
