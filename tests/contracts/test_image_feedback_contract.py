"""Tests for image feedback contract validation."""

from __future__ import annotations

import pytest

from inv_man_intake.contracts.image_feedback_contract import ImageFeedbackRecord


def test_valid_feedback_contract_record_is_accepted() -> None:
    record = ImageFeedbackRecord(
        artifact_id="va_1",
        is_informative=True,
        quality_rank=4,
        reviewer="analyst-a",
        timestamp="2026-03-01T10:00:00Z",
        notes="Useful chart with labels.",
    )

    assert record.artifact_id == "va_1"


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("artifact_id", " ", "artifact_id is required"),
        ("reviewer", " ", "reviewer is required"),
        ("timestamp", " ", "timestamp is required"),
    ),
)
def test_required_contract_fields_are_enforced(field: str, value: str, match: str) -> None:
    payload = {
        "artifact_id": "va_1",
        "is_informative": True,
        "quality_rank": 3,
        "reviewer": "analyst-a",
        "timestamp": "2026-03-01T10:00:00Z",
        "notes": None,
    }
    payload[field] = value

    with pytest.raises(ValueError, match=match):
        ImageFeedbackRecord(**payload)


def test_quality_rank_scale_is_enforced() -> None:
    with pytest.raises(ValueError, match="quality_rank must be between 1 and 5"):
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=6,
            reviewer="analyst-a",
            timestamp="2026-03-01T10:00:00Z",
        )


def test_quality_rank_must_be_integer() -> None:
    with pytest.raises(ValueError, match="quality_rank must be an integer"):
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=3.5,  # type: ignore[arg-type]
            reviewer="analyst-a",
            timestamp="2026-03-01T10:00:00Z",
        )


def test_is_informative_must_be_boolean() -> None:
    with pytest.raises(ValueError, match="is_informative must be a boolean"):
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative="yes",  # type: ignore[arg-type]
            quality_rank=3,
            reviewer="analyst-a",
            timestamp="2026-03-01T10:00:00Z",
        )


def test_timestamp_must_be_iso8601_with_timezone() -> None:
    with pytest.raises(ValueError, match="timestamp must include timezone information"):
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=3,
            reviewer="analyst-a",
            timestamp="2026-03-01T10:00:00",
        )


def test_notes_must_be_string_when_present() -> None:
    with pytest.raises(ValueError, match="notes must be a string when provided"):
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=3,
            reviewer="analyst-a",
            timestamp="2026-03-01T10:00:00Z",
            notes=123,  # type: ignore[arg-type]
        )
