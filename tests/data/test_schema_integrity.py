"""Schema integrity tests using seed fixture bundles."""

from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

import pytest

from inv_man_intake.data.fixtures import (
    correction_history_for_pointer,
    load_core_seed_rows,
    load_seed_fixture,
    reset_core_seed_tables,
    validate_provenance_pointers,
)
from inv_man_intake.data.migrations.core_schema import apply_core_schema
from inv_man_intake.data.migrations.provenance_history import apply_provenance_history_schema

FIXTURE_PATH = Path("tests/fixtures/data/core_seed_bundle.json")


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_seed_fixtures_load_into_core_schema() -> None:
    conn = _connection()
    apply_core_schema(conn)
    fixture = load_seed_fixture(FIXTURE_PATH)

    load_core_seed_rows(conn, fixture)

    assert conn.execute("SELECT COUNT(*) FROM firms").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM funds").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 2


def test_seed_fixture_reset_supports_repeatable_loads() -> None:
    conn = _connection()
    apply_core_schema(conn)
    fixture = load_seed_fixture(FIXTURE_PATH)

    load_core_seed_rows(conn, fixture)
    reset_core_seed_tables(conn)
    load_core_seed_rows(conn, fixture)

    assert conn.execute("SELECT COUNT(*) FROM firms").fetchone()[0] == 2


def test_integrity_checks_reject_orphaned_rows() -> None:
    conn = _connection()
    apply_core_schema(conn)
    fixture = load_seed_fixture(FIXTURE_PATH)
    broken = copy.deepcopy(fixture)
    broken["funds"][0]["firm_id"] = "missing_firm"

    with pytest.raises(sqlite3.IntegrityError):
        load_core_seed_rows(conn, broken)

    # Load is transactional; failed insert batch should leave no partial seed rows.
    assert conn.execute("SELECT COUNT(*) FROM firms").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM funds").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_fk_violation_rejects_fund_with_unknown_firm() -> None:
    conn = _connection()
    apply_core_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            (
                "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            ),
            (
                "fund_missing_firm",
                "firm_missing",
                "Missing Parent Fund",
                "macro",
                "multi_asset",
                "2026-03-01T09:00:00Z",
            ),
        )


def test_fk_violation_rejects_document_with_unknown_fund() -> None:
    conn = _connection()
    apply_core_schema(conn)
    conn.execute(
        "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
        ("firm_1", "Alpha Capital", None, "2026-03-01T08:00:00Z"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            (
                "INSERT INTO documents (document_id, fund_id, file_name, file_hash, received_at, "
                "version_date, source_channel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                "doc_missing_fund",
                "fund_missing",
                "missing_parent.pdf",
                "hash-missing-parent",
                "2026-03-01T09:20:00Z",
                "2026-03-01",
                "email",
                "2026-03-01T09:20:00Z",
            ),
        )


def test_fk_violation_rejects_correction_with_unknown_field() -> None:
    conn = _connection()
    apply_core_schema(conn)
    fixture = load_seed_fixture(FIXTURE_PATH)
    load_core_seed_rows(conn, fixture)
    apply_provenance_history_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            (
                "INSERT INTO field_corrections "
                "(field_id, corrected_value, reason, corrected_by, corrected_at) "
                "VALUES (?, ?, ?, ?, ?)"
            ),
            (
                "field_missing",
                "1.75%",
                "manual fix",
                "analyst@example.com",
                "2026-03-01T12:00:00Z",
            ),
        )


def test_fk_violation_rejects_extracted_field_with_unknown_document() -> None:
    conn = _connection()
    apply_core_schema(conn)
    apply_provenance_history_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            (
                "INSERT INTO extracted_fields "
                "(field_id, document_id, field_key, value, confidence, source_page, source_snippet, extracted_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                "field_missing_document",
                "doc_missing",
                "terms.management_fee",
                "2%",
                0.91,
                4,
                "Management fee: 2%",
                "2026-03-01T09:20:00Z",
            ),
        )


def test_correction_history_returns_ordered_events() -> None:
    fixture = load_seed_fixture(FIXTURE_PATH)

    history = correction_history_for_pointer(fixture, "documents.doc_alpha_q1.source_channel")

    assert [row["event_id"] for row in history] == ["evt-001", "evt-003"]
    assert history[-1]["corrected_value"] == "email"


def test_provenance_pointer_validation_accepts_known_document_fields() -> None:
    fixture = load_seed_fixture(FIXTURE_PATH)

    assert validate_provenance_pointers(fixture) == []


def test_provenance_pointer_validation_flags_unknown_targets() -> None:
    fixture = load_seed_fixture(FIXTURE_PATH)
    broken = copy.deepcopy(fixture)
    broken["corrections"][0]["provenance_pointer"] = "documents.doc_missing.source_channel"
    broken["corrections"][1]["provenance_pointer"] = "documents.doc_alpha_q1.unknown_field"

    errors = validate_provenance_pointers(broken)

    assert "unknown-document:evt-003" in errors
    assert "unknown-field:evt-001" in errors
