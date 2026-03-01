"""Tests for core firm/fund/document schema migration."""

from __future__ import annotations

import sqlite3

from inv_man_intake.data.migrations.core_schema import apply_core_schema, rollback_core_schema


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def _index_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    return {row[0] for row in rows}


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_apply_core_schema_creates_tables_and_indexes() -> None:
    conn = _connection()

    apply_core_schema(conn)

    assert {"firms", "funds", "documents"}.issubset(_table_names(conn))
    assert {"idx_funds_firm_id", "idx_documents_fund_id", "idx_documents_received_at"}.issubset(
        _index_names(conn)
    )


def test_apply_core_schema_enforces_foreign_key_relationships() -> None:
    conn = _connection()
    apply_core_schema(conn)

    conn.execute(
        "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
        ("firm_1", "Alpha Capital", None, "2026-03-01T09:00:00Z"),
    )
    conn.execute(
        (
            "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        ),
        (
            "fund_1",
            "firm_1",
            "Alpha Market Neutral",
            "market_neutral",
            "equity_market_neutral",
            "2026-03-01T09:00:00Z",
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
            "hash-1",
            "2026-03-01T09:00:00Z",
            "2026-03-01",
            "email",
            "2026-03-01T09:00:00Z",
        ),
    )

    count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
    assert count is not None
    assert count[0] == 1


def test_rollback_core_schema_drops_tables() -> None:
    conn = _connection()
    apply_core_schema(conn)
    rollback_core_schema(conn)

    assert "firms" not in _table_names(conn)
    assert "funds" not in _table_names(conn)
    assert "documents" not in _table_names(conn)
