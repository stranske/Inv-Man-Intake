"""Seed fixture helpers for schema integrity tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast

_VALID_POINTER_PREFIX = "documents."
_DOCUMENT_SCHEMA_FIELDS: frozenset[str] = frozenset(
    {
        "document_id",
        "fund_id",
        "file_name",
        "file_hash",
        "received_at",
        "version_date",
        "source_channel",
        "created_at",
    }
)


def load_seed_fixture(path: Path | str) -> dict[str, Any]:
    """Load a JSON fixture bundle from disk."""
    fixture_path = Path(path)
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Seed fixture root must be a JSON object.")
    return cast(dict[str, Any], data)


def reset_core_seed_tables(connection: sqlite3.Connection) -> None:
    """Clear core seed tables in child-to-parent order for repeatable reloads."""
    connection.execute("DELETE FROM documents")
    connection.execute("DELETE FROM funds")
    connection.execute("DELETE FROM firms")
    connection.commit()


def load_core_seed_rows(connection: sqlite3.Connection, fixture: dict[str, Any]) -> None:
    """Insert core firm/fund/document fixture rows into sqlite."""
    with connection:
        for firm in fixture.get("firms", []):
            connection.execute(
                "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
                (firm["firm_id"], firm["legal_name"], firm.get("aliases_json"), firm["created_at"]),
            )

        for fund in fixture.get("funds", []):
            connection.execute(
                (
                    "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)"
                ),
                (
                    fund["fund_id"],
                    fund["firm_id"],
                    fund["fund_name"],
                    fund.get("strategy"),
                    fund.get("asset_class"),
                    fund["created_at"],
                ),
            )

        for document in fixture.get("documents", []):
            connection.execute(
                (
                    "INSERT INTO documents (document_id, fund_id, file_name, file_hash, received_at, "
                    "version_date, source_channel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    document["document_id"],
                    document["fund_id"],
                    document["file_name"],
                    document["file_hash"],
                    document["received_at"],
                    document["version_date"],
                    document["source_channel"],
                    document["created_at"],
                ),
            )


def correction_history_for_pointer(fixture: dict[str, Any], pointer: str) -> list[dict[str, Any]]:
    """Return correction history rows for a pointer sorted by timestamp."""
    history = [
        row for row in fixture.get("corrections", []) if row.get("provenance_pointer") == pointer
    ]
    return sorted(history, key=lambda row: (row["corrected_at"], row["event_id"]))


def validate_provenance_pointers(fixture: dict[str, Any]) -> list[str]:
    """Validate that provenance pointers use a known document + field path."""
    errors: list[str] = []
    documents = {row["document_id"]: row for row in fixture.get("documents", [])}

    for row in fixture.get("corrections", []):
        pointer = row.get("provenance_pointer", "")
        if not isinstance(pointer, str) or not pointer.startswith(_VALID_POINTER_PREFIX):
            errors.append(f"invalid-pointer-format:{row.get('event_id', 'unknown')}")
            continue

        parts = pointer.split(".")
        if len(parts) != 3:
            errors.append(f"invalid-pointer-format:{row.get('event_id', 'unknown')}")
            continue

        _, document_id, field_name = parts
        document = documents.get(document_id)
        if document is None:
            errors.append(f"unknown-document:{row.get('event_id', 'unknown')}")
            continue

        if field_name not in _DOCUMENT_SCHEMA_FIELDS:
            errors.append(f"unknown-field:{row.get('event_id', 'unknown')}")

    return errors
