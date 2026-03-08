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


def test_correction_history_returns_ordered_events() -> None:
    fixture = load_seed_fixture(FIXTURE_PATH)

    history = correction_history_for_pointer(fixture, "documents.doc_alpha_q1.strategy")

    assert [row["event_id"] for row in history] == ["evt-001", "evt-003"]
    assert history[-1]["corrected_value"] == "long_short_equity"


def test_provenance_pointer_validation_accepts_known_document_fields() -> None:
    fixture = load_seed_fixture(FIXTURE_PATH)

    assert validate_provenance_pointers(fixture) == []


def test_provenance_pointer_validation_flags_unknown_targets() -> None:
    fixture = load_seed_fixture(FIXTURE_PATH)
    broken = copy.deepcopy(fixture)
    broken["corrections"][0]["provenance_pointer"] = "documents.doc_missing.strategy"
    broken["corrections"][1]["provenance_pointer"] = "documents.doc_alpha_q1.unknown_field"

    errors = validate_provenance_pointers(broken)

    assert "unknown-document:evt-003" in errors
    assert "unknown-field:evt-001" in errors
