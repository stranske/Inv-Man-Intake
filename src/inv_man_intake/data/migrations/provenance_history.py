"""Migration entrypoints for extracted field provenance/correction tables."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_UP_PATH = _SQL_DIR / "0002_field_provenance_history.up.sql"
_DOWN_PATH = _SQL_DIR / "0002_field_provenance_history.down.sql"


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def apply_provenance_history_schema(connection: sqlite3.Connection) -> None:
    """Apply extracted-field and correction-history schema."""
    connection.executescript(_read_sql(_UP_PATH))
    connection.commit()


def rollback_provenance_history_schema(connection: sqlite3.Connection) -> None:
    """Rollback extracted-field and correction-history schema."""
    connection.executescript(_read_sql(_DOWN_PATH))
    connection.commit()
