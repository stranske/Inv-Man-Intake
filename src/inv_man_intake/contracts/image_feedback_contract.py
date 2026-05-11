"""Contract for human visual-artifact feedback records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
        object.__setattr__(self, "artifact_id", self.artifact_id.strip())
        object.__setattr__(self, "reviewer", self.reviewer.strip())
        object.__setattr__(self, "timestamp", _normalize_timestamp(self.timestamp))
        validate_image_feedback(self)


def validate_image_feedback(record: ImageFeedbackRecord) -> None:
    """Validate required feedback fields and the supported rank scale."""

    if isinstance(record.is_informative, bool) is False:
        raise ValueError("is_informative must be a boolean")
    if isinstance(record.quality_rank, bool) or isinstance(record.quality_rank, int) is False:
        raise ValueError("quality_rank must be an integer")
    if not record.artifact_id.strip():
        raise ValueError("artifact_id is required")
    if not record.reviewer.strip():
        raise ValueError("reviewer is required")
    if not record.timestamp.strip():
        raise ValueError("timestamp is required")
    if record.notes is not None and isinstance(record.notes, str) is False:
        raise ValueError("notes must be a string when provided")
    if not MIN_QUALITY_RANK <= record.quality_rank <= MAX_QUALITY_RANK:
        raise ValueError(f"quality_rank must be between {MIN_QUALITY_RANK} and {MAX_QUALITY_RANK}")
    _normalize_timestamp(record.timestamp)


def _normalize_timestamp(value: str) -> str:
    normalized = value.strip()
    normalized = normalized.removesuffix("Z") + "+00:00" if normalized.endswith("Z") else normalized
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone information")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
