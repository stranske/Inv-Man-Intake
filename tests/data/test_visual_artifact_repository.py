"""Tests for visual artifact repository persistence behavior."""

from __future__ import annotations

import sqlite3

from inv_man_intake.data.migrations.core_schema import apply_core_schema
from inv_man_intake.data.provenance import VisualArtifactRecord
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
