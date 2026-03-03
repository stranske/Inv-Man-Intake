"""Tests for core firm/fund/document schema migration."""

from __future__ import annotations

import sqlite3

import pytest

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


def _table_columns(connection: sqlite3.Connection, table_name: str) -> dict[str, tuple[str, int]]:
    rows = connection.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return {row[1]: (row[2], row[3]) for row in rows}


def test_apply_core_schema_creates_tables_and_indexes() -> None:
    conn = _connection()

    apply_core_schema(conn)

    assert {"firms", "funds", "documents"}.issubset(_table_names(conn))
    assert {"idx_funds_firm_id", "idx_documents_fund_id", "idx_documents_received_at"}.issubset(
        _index_names(conn)
    )


def test_apply_core_schema_defines_required_columns() -> None:
    conn = _connection()
    apply_core_schema(conn)

    firm_columns = _table_columns(conn, "firms")
    assert firm_columns["firm_id"] == ("TEXT", 0)
    assert firm_columns["legal_name"] == ("TEXT", 1)
    assert firm_columns["aliases_json"] == ("TEXT", 0)
    assert firm_columns["created_at"] == ("TEXT", 1)

    fund_columns = _table_columns(conn, "funds")
    assert fund_columns["fund_id"] == ("TEXT", 0)
    assert fund_columns["firm_id"] == ("TEXT", 1)
    assert fund_columns["fund_name"] == ("TEXT", 1)
    assert fund_columns["strategy"] == ("TEXT", 0)
    assert fund_columns["asset_class"] == ("TEXT", 0)
    assert fund_columns["created_at"] == ("TEXT", 1)

    document_columns = _table_columns(conn, "documents")
    assert document_columns["document_id"] == ("TEXT", 0)
    assert document_columns["fund_id"] == ("TEXT", 1)
    assert document_columns["file_name"] == ("TEXT", 1)
    assert document_columns["file_hash"] == ("TEXT", 1)
    assert document_columns["received_at"] == ("TEXT", 1)
    assert document_columns["version_date"] == ("TEXT", 1)
    assert document_columns["source_channel"] == ("TEXT", 1)
    assert document_columns["created_at"] == ("TEXT", 1)


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


def test_apply_core_schema_rejects_orphaned_children() -> None:
    conn = _connection()
    apply_core_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            (
                "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (
                "fund_orphan",
                "missing_firm",
                "Orphan Fund",
                "long_short",
                "equity",
                "2026-03-01T09:00:00Z",
            ),
        )

    conn.execute(
        "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
        ("firm_1", "Alpha Capital", None, "2026-03-01T09:00:00Z"),
    )
    conn.execute(
        (
            "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        ),
        ("fund_1", "firm_1", "Alpha Market Neutral", None, None, "2026-03-01T09:00:00Z"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            (
                "INSERT INTO documents (document_id, fund_id, file_name, file_hash, received_at, "
                "version_date, source_channel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                "doc_orphan",
                "missing_fund",
                "orphan.pdf",
                "hash-orphan",
                "2026-03-01T09:00:00Z",
                "2026-03-01",
                "email",
                "2026-03-01T09:00:00Z",
            ),
        )


def test_apply_core_schema_cascades_deletes_down_hierarchy() -> None:
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
        ("fund_1", "firm_1", "Alpha Market Neutral", None, None, "2026-03-01T09:00:00Z"),
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

    conn.execute("DELETE FROM firms WHERE firm_id = ?", ("firm_1",))

    fund_count = conn.execute("SELECT COUNT(*) FROM funds").fetchone()
    document_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()
    assert fund_count is not None
    assert document_count is not None
    assert fund_count[0] == 0
    assert document_count[0] == 0


def test_apply_core_schema_rejects_blank_required_identifiers() -> None:
    conn = _connection()
    apply_core_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
            ("", "Alpha Capital", None, "2026-03-01T09:00:00Z"),
        )


def test_rollback_core_schema_drops_tables() -> None:
    conn = _connection()
    apply_core_schema(conn)
    rollback_core_schema(conn)

    assert "firms" not in _table_names(conn)
    assert "funds" not in _table_names(conn)
    assert "documents" not in _table_names(conn)


def test_rollback_core_schema_allows_clean_reapply() -> None:
    conn = _connection()
    apply_core_schema(conn)
    rollback_core_schema(conn)
    apply_core_schema(conn)

    conn.execute(
        "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
        ("firm_1", "Alpha Capital", None, "2026-03-01T09:00:00Z"),
    )
    count = conn.execute("SELECT COUNT(*) FROM firms").fetchone()
    assert count is not None
    assert count[0] == 1
