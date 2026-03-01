"""Tests for provenance and correction-history schema behavior."""

from __future__ import annotations

import sqlite3

from inv_man_intake.data.migrations.provenance_history import apply_provenance_history_schema
from inv_man_intake.data.provenance import ExtractedFieldRecord
from inv_man_intake.data.repository import FieldProvenanceRepository


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "CREATE TABLE documents (document_id TEXT PRIMARY KEY, file_name TEXT NOT NULL, received_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO documents (document_id, file_name, received_at) VALUES (?, ?, ?)",
        ("doc_1", "alpha_deck.pdf", "2026-03-01T09:00:00Z"),
    )
    conn.commit()
    return conn


def test_apply_provenance_schema_creates_tables() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)

    tables = _table_names(conn)
    assert "extracted_fields" in tables
    assert "field_corrections" in tables


def test_corrections_are_append_only_and_latest_value_comes_from_last_correction() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)

    repo.insert_extracted_field(
        ExtractedFieldRecord(
            field_id="field_1",
            document_id="doc_1",
            field_key="terms.management_fee",
            value="2%",
            confidence=0.82,
            source_page=4,
            source_snippet="Management fee: 2%",
            extracted_at="2026-03-01T09:05:00Z",
        )
    )

    repo.append_correction(
        field_id="field_1",
        corrected_value="1.9%",
        corrected_at="2026-03-01T10:00:00Z",
        reason="Analyst correction",
        corrected_by="analyst@example.com",
    )
    repo.append_correction(
        field_id="field_1",
        corrected_value="1.85%",
        corrected_at="2026-03-01T11:00:00Z",
        reason="Updated term sheet",
        corrected_by="analyst@example.com",
    )

    assert repo.get_latest_value("field_1") == "1.85%"

    history = repo.get_correction_history("field_1")
    assert len(history) == 2
    assert history[0].corrected_value == "1.9%"
    assert history[1].corrected_value == "1.85%"


def test_latest_value_returns_original_when_no_correction_exists() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)

    repo.insert_extracted_field(
        ExtractedFieldRecord(
            field_id="field_2",
            document_id="doc_1",
            field_key="personnel.cio",
            value="Jane Doe",
            confidence=0.91,
            source_page=2,
            source_snippet="Chief Investment Officer: Jane Doe",
            extracted_at="2026-03-01T09:03:00Z",
        )
    )

    assert repo.get_latest_value("field_2") == "Jane Doe"
