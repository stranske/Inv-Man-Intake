"""Tests for provenance and correction-history schema behavior."""

from __future__ import annotations

import sqlite3

import pytest

from inv_man_intake.data.migrations.core_schema import apply_core_schema
from inv_man_intake.data.migrations.provenance_history import apply_provenance_history_schema
from inv_man_intake.data.provenance import ExtractedFieldRecord
from inv_man_intake.data.repository import FieldProvenanceRepository


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


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
            "alpha_deck.pdf",
            "hash_doc_1",
            "2026-03-01T09:00:00Z",
            "2026-03-01",
            "email",
            "2026-03-01T09:00:00Z",
        ),
    )
    conn.commit()
    return conn


def test_apply_provenance_schema_requires_core_documents_table() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")

    with pytest.raises(RuntimeError, match="documents table is required"):
        apply_provenance_history_schema(conn)


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

    repo.write_initial_extraction(
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

    repo.write_correction_append(
        field_id="field_1",
        corrected_value="1.9%",
        corrected_at="2026-03-01T10:00:00Z",
        reason="Analyst correction",
        corrected_by="analyst@example.com",
    )
    repo.write_correction_append(
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


def test_correction_history_orders_by_corrected_at_not_insert_order() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)

    repo.write_initial_extraction(
        ExtractedFieldRecord(
            field_id="field_3",
            document_id="doc_1",
            field_key="terms.lockup",
            value="12 months",
            confidence=0.75,
            source_page=6,
            source_snippet="Lock-up: 12 months",
            extracted_at="2026-03-01T09:05:00Z",
        )
    )
    repo.write_correction_append(
        field_id="field_3",
        corrected_value="18 months",
        corrected_at="2026-03-03T09:00:00Z",
        reason="later update",
    )
    repo.write_correction_append(
        field_id="field_3",
        corrected_value="15 months",
        corrected_at="2026-03-02T09:00:00Z",
        reason="backfilled correction",
    )

    history = repo.get_correction_history("field_3")
    assert [entry.corrected_value for entry in history] == ["15 months", "18 months"]


def test_latest_value_returns_original_when_no_correction_exists() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)

    repo.write_initial_extraction(
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

    history = repo.get_value_history("field_2")
    assert len(history) == 1
    assert history[0].source == "extracted"
    assert history[0].value == "Jane Doe"


def test_write_correction_append_keeps_original_extracted_value() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)
    repo.write_initial_extraction(
        ExtractedFieldRecord(
            field_id="field_4",
            document_id="doc_1",
            field_key="terms.hurdle_rate",
            value="8%",
            confidence=0.88,
            source_page=5,
            source_snippet="Hurdle rate: 8%",
            extracted_at="2026-03-01T09:08:00Z",
        )
    )

    repo.write_correction_append(
        field_id="field_4",
        corrected_value="7%",
        corrected_at="2026-03-01T10:08:00Z",
        reason="Typo in deck",
    )

    original_row = conn.execute(
        "SELECT value FROM extracted_fields WHERE field_id = ?",
        ("field_4",),
    ).fetchone()
    assert original_row is not None
    assert str(original_row[0]) == "8%"
    assert repo.get_latest_value("field_4") == "7%"
    assert [entry.value for entry in repo.get_value_history("field_4")] == ["8%", "7%"]


def test_get_value_history_orders_by_effective_time_and_matches_latest() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)
    repo.write_initial_extraction(
        ExtractedFieldRecord(
            field_id="field_6",
            document_id="doc_1",
            field_key="terms.redemption_notice",
            value="90 days",
            confidence=0.84,
            source_page=8,
            source_snippet="Redemption notice: 90 days",
            extracted_at="2026-03-01T09:10:00Z",
        )
    )
    repo.write_correction_append(
        field_id="field_6",
        corrected_value="75 days",
        corrected_at="2026-03-03T09:00:00Z",
        reason="later update",
    )
    repo.write_correction_append(
        field_id="field_6",
        corrected_value="60 days",
        corrected_at="2026-03-02T09:00:00Z",
        reason="backfilled correction",
    )

    history = repo.get_value_history("field_6")
    assert [entry.value for entry in history] == ["90 days", "60 days", "75 days"]
    assert history[0].source == "extracted"
    assert [entry.source for entry in history[1:]] == ["corrected", "corrected"]
    assert repo.get_latest_value("field_6") == history[-1].value


def test_write_correction_append_unknown_field_raises_key_error() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)

    with pytest.raises(KeyError, match="field_id=missing_field not found"):
        repo.write_correction_append(
            field_id="missing_field",
            corrected_value="new value",
            corrected_at="2026-03-01T10:00:00Z",
        )


def test_history_queries_unknown_field_raise_key_error() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)

    with pytest.raises(KeyError, match="field_id=missing_field not found"):
        repo.get_latest_value("missing_field")
    with pytest.raises(KeyError, match="field_id=missing_field not found"):
        repo.get_correction_history("missing_field")
    with pytest.raises(KeyError, match="field_id=missing_field not found"):
        repo.get_value_history("missing_field")


def test_write_initial_extraction_unknown_document_raises_key_error() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)

    with pytest.raises(KeyError, match="document_id=missing_doc not found"):
        repo.write_initial_extraction(
            ExtractedFieldRecord(
                field_id="field_missing_doc",
                document_id="missing_doc",
                field_key="terms.management_fee",
                value="2%",
                confidence=0.82,
                source_page=4,
                source_snippet="Management fee: 2%",
                extracted_at="2026-03-01T09:05:00Z",
            )
        )


def test_write_initial_extraction_duplicate_field_raises_key_error() -> None:
    conn = _connection()
    apply_provenance_history_schema(conn)
    repo = FieldProvenanceRepository(conn)

    record = ExtractedFieldRecord(
        field_id="field_5",
        document_id="doc_1",
        field_key="terms.redemption_notice",
        value="60 days",
        confidence=0.84,
        source_page=8,
        source_snippet="Redemption notice: 60 days",
        extracted_at="2026-03-01T09:10:00Z",
    )
    repo.write_initial_extraction(record)

    with pytest.raises(KeyError, match="field_id=field_5 already exists"):
        repo.write_initial_extraction(record)
