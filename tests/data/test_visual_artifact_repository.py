"""Tests for visual artifact repository persistence behavior."""

from __future__ import annotations

import sqlite3

import pytest

from inv_man_intake.data.migrations.core_schema import apply_core_schema
from inv_man_intake.data.provenance import VisualArtifactFeedbackRecord, VisualArtifactRecord
from inv_man_intake.data.repository import VisualArtifactRepository


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


def test_visual_artifact_repository_round_trip() -> None:
    conn = _connection()
    repo = VisualArtifactRepository(conn)
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

    rows = repo.list_artifacts("doc_1")
    assert len(rows) == 1
    assert rows[0].artifact_id == "va_1"
    assert rows[0].source_page == 2
    assert rows[0].sha256 == "abc123"


def test_visual_artifact_repository_preserves_slide_coordinates() -> None:
    conn = _connection()
    repo = VisualArtifactRepository(conn)
    repo.ensure_schema()

    repo.insert_artifact(
        VisualArtifactRecord(
            artifact_id="va_slide_1",
            document_id="doc_1",
            source_type="pptx",
            source_page=None,
            source_slide=4,
            source_ref="rId7",
            storage_path="artifacts/doc_1/pptx/slide-4/image3.png",
            sha256="def456",
            mime_type="image/png",
            byte_size=830,
            extracted_at="2026-03-01T09:11:00Z",
        )
    )

    rows = repo.list_artifacts("doc_1")
    assert rows[0].source_slide == 4
    assert rows[0].source_ref == "rId7"


def test_visual_artifact_repository_requires_core_schema_before_ensure_schema() -> None:
    conn = sqlite3.connect(":memory:")
    repo = VisualArtifactRepository(conn)

    with pytest.raises(RuntimeError, match="documents table missing"):
        repo.ensure_schema()


def test_visual_artifact_repository_enables_foreign_keys() -> None:
    conn = sqlite3.connect(":memory:")
    repo = VisualArtifactRepository(conn)

    assert repo._connection.execute("PRAGMA foreign_keys").fetchone() == (1,)


def test_visual_artifact_repository_insert_is_idempotent_for_same_artifact() -> None:
    conn = _connection()
    repo = VisualArtifactRepository(conn)
    repo.ensure_schema()

    record = VisualArtifactRecord(
        artifact_id="va_dup_1",
        document_id="doc_1",
        source_type="pdf",
        source_page=2,
        source_slide=None,
        source_ref="pdf-object-12",
        storage_path="artifacts/doc_1/pdf/page-2/object-12.bin",
        sha256="dup123",
        mime_type="image/jpeg",
        byte_size=1240,
        extracted_at="2026-03-01T09:10:00Z",
    )

    repo.insert_artifact(record)
    repo.insert_artifact(record)

    rows = repo.list_artifacts("doc_1")
    assert [row.artifact_id for row in rows] == ["va_dup_1"]


def _seed_feedback_for_bound_tests(repo: VisualArtifactRepository) -> None:
    repo.ensure_schema()
    repo.ensure_feedback_schema()
    repo.insert_artifact(
        VisualArtifactRecord(
            artifact_id="va_bound_1",
            document_id="doc_1",
            source_type="pdf",
            source_page=1,
            source_slide=None,
            source_ref="pdf-object-1",
            storage_path="artifacts/doc_1/pdf/page-1/object.bin",
            sha256="hash-bound-1",
            mime_type="image/jpeg",
            byte_size=1024,
            extracted_at="2026-03-01T09:00:00Z",
        )
    )
    for reviewed_at, reviewer in (
        ("2026-03-01T09:30:00Z", "analyst-a"),
        ("2026-03-01T10:30:00Z", "analyst-b"),
        ("2026-03-01T11:30:00Z", "analyst-c"),
    ):
        repo.upsert_feedback(
            VisualArtifactFeedbackRecord(
                artifact_id="va_bound_1",
                is_informative=True,
                quality_rank=3,
                reviewer=reviewer,
                reviewed_at=reviewed_at,
                notes=None,
            )
        )


def test_list_all_feedback_normalizes_offset_bounds_to_canonical_utc() -> None:
    repo = VisualArtifactRepository(_connection())
    _seed_feedback_for_bound_tests(repo)

    # Stored values are canonical `...Z`. Bounds passed as `+00:00` would
    # otherwise lose the 10:30:00Z row to a raw TEXT comparison, since
    # "2026-03-01T10:00:00+00:00" > "2026-03-01T10:00:00Z" lexicographically.
    rows = repo.list_all_feedback(
        reviewed_from="2026-03-01T10:00:00+00:00",
        reviewed_to="2026-03-01T11:00:00+00:00",
    )

    assert [row.reviewer for row in rows] == ["analyst-b"]


def test_list_all_feedback_normalizes_non_utc_offset_to_utc() -> None:
    repo = VisualArtifactRepository(_connection())
    _seed_feedback_for_bound_tests(repo)

    # 11:30+02:00 == 09:30Z, 13:30+02:00 == 11:30Z; full inclusive range covers
    # all three stored rows (09:30Z, 10:30Z, 11:30Z). The point of the test is
    # that the +02:00 bounds are normalized rather than text-compared against
    # the canonical `...Z` stored values.
    rows = repo.list_all_feedback(
        reviewed_from="2026-03-01T11:30:00+02:00",
        reviewed_to="2026-03-01T13:30:00+02:00",
    )

    assert [row.reviewer for row in rows] == ["analyst-a", "analyst-b", "analyst-c"]

    # Narrower window: 12:00+02:00 == 10:00Z, 13:00+02:00 == 11:00Z → only analyst-b.
    rows = repo.list_all_feedback(
        reviewed_from="2026-03-01T12:00:00+02:00",
        reviewed_to="2026-03-01T13:00:00+02:00",
    )

    assert [row.reviewer for row in rows] == ["analyst-b"]


def test_list_all_feedback_rejects_invalid_iso8601_bound() -> None:
    repo = VisualArtifactRepository(_connection())
    repo.ensure_schema()
    repo.ensure_feedback_schema()

    with pytest.raises(ValueError, match="reviewed_from must be ISO-8601"):
        repo.list_all_feedback(reviewed_from="not-a-timestamp")
    with pytest.raises(ValueError, match="reviewed_to must be ISO-8601"):
        repo.list_all_feedback(reviewed_to="2026-13-99T99:99:99Z")


def test_list_all_feedback_rejects_naive_bound() -> None:
    repo = VisualArtifactRepository(_connection())
    repo.ensure_schema()
    repo.ensure_feedback_schema()

    with pytest.raises(ValueError, match="reviewed_from must include timezone"):
        repo.list_all_feedback(reviewed_from="2026-03-01T10:00:00")
    with pytest.raises(ValueError, match="reviewed_to must include timezone"):
        repo.list_all_feedback(reviewed_to="2026-03-01T11:00:00")


def test_list_all_feedback_rejects_empty_bound() -> None:
    repo = VisualArtifactRepository(_connection())
    repo.ensure_schema()
    repo.ensure_feedback_schema()

    with pytest.raises(ValueError, match="reviewed_from must be a non-empty"):
        repo.list_all_feedback(reviewed_from="   ")
