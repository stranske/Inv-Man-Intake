"""Contract for human visual-artifact feedback records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MIN_QUALITY_RANK = 1
MAX_QUALITY_RANK = 5


@dataclass(frozen=True)
class ImageFeedbackRecord:
    """Human review feedback for one extracted visual artifact."""

    artifact_id: str
    is_informative: bool
    quality_rank: int
    reviewer: str
    timestamp: str
    notes: str | None = None

    def __post_init__(self) -> None:
        validate_image_feedback(self)


def validate_image_feedback(record: ImageFeedbackRecord) -> None:
    """Validate required feedback fields and the supported rank scale."""

    if not record.artifact_id.strip():
        raise ValueError("artifact_id is required")
    if not record.reviewer.strip():
        raise ValueError("reviewer is required")
    if not record.timestamp.strip():
        raise ValueError("timestamp is required")
    if not MIN_QUALITY_RANK <= record.quality_rank <= MAX_QUALITY_RANK:
        raise ValueError(f"quality_rank must be between {MIN_QUALITY_RANK} and {MAX_QUALITY_RANK}")
    _parse_timestamp(record.timestamp)


def _parse_timestamp(value: str) -> None:
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
