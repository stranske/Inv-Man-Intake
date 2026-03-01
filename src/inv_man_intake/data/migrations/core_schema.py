"""Apply and rollback core schema migrations for firm/fund/document entities."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SQL_DIR = Path(__file__).resolve().parent / "sql"
_UP_PATH = _SQL_DIR / "0001_core_firm_fund_document.up.sql"
_DOWN_PATH = _SQL_DIR / "0001_core_firm_fund_document.down.sql"


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def apply_core_schema(connection: sqlite3.Connection) -> None:
    """Apply the core schema migration to the provided sqlite connection."""
    connection.executescript(_read_sql(_UP_PATH))
    connection.commit()


def rollback_core_schema(connection: sqlite3.Connection) -> None:
    """Rollback the core schema migration from the provided sqlite connection."""
    connection.executescript(_read_sql(_DOWN_PATH))
    connection.commit()
