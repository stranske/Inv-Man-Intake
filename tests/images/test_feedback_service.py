"""Tests for visual artifact feedback capture and persistence."""

from __future__ import annotations

import sqlite3

import pytest

from inv_man_intake.contracts.image_feedback_contract import ImageFeedbackRecord
from inv_man_intake.data.migrations.core_schema import apply_core_schema
from inv_man_intake.data.provenance import VisualArtifactRecord
from inv_man_intake.data.repository import VisualArtifactRepository
from inv_man_intake.images.feedback_service import VisualArtifactFeedbackService


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_core_schema(conn)
    conn.execute(
        "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
        ("firm_1", "Alpha Capital", None, "2026-03-01T08:00:00Z"),
    )
    conn.execute(
        (
            "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        ),
        (
            "fund_1",
            "firm_1",
            "Alpha Fund",
            "market_neutral",
            "equity_market_neutral",
            "2026-03-01T08:30:00Z",
        ),
    )
    conn.execute(
        (
            "INSERT INTO documents (document_id, fund_id, file_name, file_hash, received_at, "
            "version_date, source_channel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            "doc_1",
            "fund_1",
            "manager_deck.pdf",
            "hash_doc_1",
            "2026-03-01T09:00:00Z",
            "2026-03-01",
            "email",
            "2026-03-01T09:00:00Z",
        ),
    )
    conn.commit()
    return conn


def _repository() -> VisualArtifactRepository:
    repo = VisualArtifactRepository(_connection())
    repo.ensure_schema()
    repo.insert_artifact(
        VisualArtifactRecord(
            artifact_id="va_1",
            document_id="doc_1",
            source_type="pdf",
            source_page=2,
            source_slide=None,
            source_ref="pdf-object-12",
            storage_path="artifacts/doc_1/pdf/page-2/object-12.bin",
            sha256="abc123",
            mime_type="image/jpeg",
            byte_size=1240,
            extracted_at="2026-03-01T09:10:00Z",
        )
    )
    repo.ensure_feedback_schema()
    return repo


def test_feedback_records_can_be_created_and_retrieved_per_artifact() -> None:
    service = VisualArtifactFeedbackService(_repository())
    record = ImageFeedbackRecord(
        artifact_id="va_1",
        is_informative=True,
        quality_rank=5,
        reviewer="analyst-a",
        timestamp="2026-03-01T10:00:00Z",
        notes="Useful exposure chart.",
    )

    result = service.record_feedback(record)

    assert result.replaced_existing is False
    assert service.get_feedback("va_1", "analyst-a") == record
    assert service.list_feedback("va_1") == (record,)


def test_repeated_reviewer_feedback_updates_without_duplicate_rows() -> None:
    service = VisualArtifactFeedbackService(_repository())
    original = ImageFeedbackRecord(
        artifact_id="va_1",
        is_informative=False,
        quality_rank=2,
        reviewer="analyst-a",
        timestamp="2026-03-01T10:00:00Z",
        notes="Mostly decorative.",
    )
    update = ImageFeedbackRecord(
        artifact_id="va_1",
        is_informative=True,
        quality_rank=4,
        reviewer="analyst-a",
        timestamp="2026-03-01T10:05:00Z",
        notes="Actually useful after zooming in.",
    )

    assert service.record_feedback(original).replaced_existing is False
    assert service.record_feedback(update).replaced_existing is True

    assert service.list_feedback("va_1") == (update,)


def test_feedback_normalizes_identity_and_review_time_before_persistence() -> None:
    service = VisualArtifactFeedbackService(_repository())
    record = ImageFeedbackRecord(
        artifact_id=" va_1 ",
        is_informative=True,
        quality_rank=5,
        reviewer=" analyst-a ",
        timestamp="2026-03-01T05:00:00-05:00",
        notes="Useful exposure chart.",
    )

    result = service.record_feedback(record)

    assert result.replaced_existing is False
    assert result.record.artifact_id == "va_1"
    assert result.record.reviewer == "analyst-a"
    assert result.record.timestamp == "2026-03-01T10:00:00Z"
    assert service.get_feedback("va_1", "analyst-a") == result.record


def test_feedback_list_sorts_by_normalized_review_time() -> None:
    service = VisualArtifactFeedbackService(_repository())
    later = ImageFeedbackRecord(
        artifact_id="va_1",
        is_informative=True,
        quality_rank=5,
        reviewer="analyst-b",
        timestamp="2026-03-01T10:30:00Z",
    )
    earlier = ImageFeedbackRecord(
        artifact_id="va_1",
        is_informative=True,
        quality_rank=4,
        reviewer="analyst-a",
        timestamp="2026-03-01T05:00:00-05:00",
    )

    service.record_feedback(later)
    service.record_feedback(earlier)

    assert service.list_feedback("va_1") == (earlier, later)


def test_feedback_validation_enforces_rank_scale_required_fields_and_fk() -> None:
    with pytest.raises(ValueError, match="quality_rank must be between 1 and 5"):
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=6,
            reviewer="analyst-a",
            timestamp="2026-03-01T10:00:00Z",
        )

    with pytest.raises(ValueError, match="reviewer is required"):
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=3,
            reviewer=" ",
            timestamp="2026-03-01T10:00:00Z",
        )

    service = VisualArtifactFeedbackService(_repository())
    with pytest.raises(sqlite3.IntegrityError):
        service.record_feedback(
            ImageFeedbackRecord(
                artifact_id="missing",
                is_informative=True,
                quality_rank=3,
                reviewer="analyst-a",
                timestamp="2026-03-01T10:00:00Z",
            )
        )
