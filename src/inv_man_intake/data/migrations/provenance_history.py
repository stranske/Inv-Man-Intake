"""Migration entrypoints for extracted field provenance/correction tables."""

from __future__ import annotations

import sqlite3
from importlib import resources

_UP_RESOURCE = "0002_field_provenance_history.up.sql"
_DOWN_RESOURCE = "0002_field_provenance_history.down.sql"


def _read_sql(resource_name: str) -> str:
    base = (
        resources.files(__package__)
        if __package__ is not None
        else resources.files(__name__.rpartition(".")[0])
    )
    return (base / "sql" / resource_name).read_text(encoding="utf-8")


def apply_provenance_history_schema(connection: sqlite3.Connection) -> None:
    """Apply extracted-field and correction-history schema."""
    documents_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'documents'"
    ).fetchone()
    if documents_table is None:
        raise RuntimeError(
            "documents table is required before applying provenance history schema; "
            "run core schema migration first"
        )
    connection.executescript(_read_sql(_UP_RESOURCE))
    connection.commit()


def rollback_provenance_history_schema(connection: sqlite3.Connection) -> None:
    """Rollback extracted-field and correction-history schema."""
    connection.executescript(_read_sql(_DOWN_RESOURCE))
    connection.commit()
