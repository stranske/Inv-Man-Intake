"""Apply and rollback core schema migrations for firm/fund/document entities."""

from __future__ import annotations

import sqlite3
from importlib import resources

_UP_RESOURCE = "0001_core_firm_fund_document.up.sql"
_DOWN_RESOURCE = "0001_core_firm_fund_document.down.sql"


def _read_sql(resource_name: str) -> str:
    """Read a SQL migration script from the packaged sql directory.

    Uses importlib.resources so the SQL files are resolved correctly
    whether the package is run from a source checkout or installed as a wheel.
    """
    base = (
        resources.files(__package__)
        if __package__ is not None
        else resources.files(__name__.rpartition(".")[0])
    )
    return (base / "sql" / resource_name).read_text(encoding="utf-8")


def apply_core_schema(connection: sqlite3.Connection) -> None:
    """Apply the core schema migration to the provided sqlite connection."""
    connection.executescript(_read_sql(_UP_RESOURCE))
    connection.commit()


def rollback_core_schema(connection: sqlite3.Connection) -> None:
    """Rollback the core schema migration from the provided sqlite connection."""
    connection.executescript(_read_sql(_DOWN_RESOURCE))
    connection.commit()
