"""Tests that migration contract documentation matches the core schema SQL."""

from __future__ import annotations

import re
from pathlib import Path

DOC_PATH = Path("docs/contracts/core_schema_migration.md")
UP_SQL_PATH = Path("src/inv_man_intake/data/migrations/sql/0001_core_firm_fund_document.up.sql")
DOWN_SQL_PATH = Path("src/inv_man_intake/data/migrations/sql/0001_core_firm_fund_document.down.sql")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_core_migration_docs_reference_existing_migration_files() -> None:
    doc_text = _read_text(DOC_PATH)

    assert DOC_PATH.exists()
    assert UP_SQL_PATH.exists()
    assert DOWN_SQL_PATH.exists()
    assert str(UP_SQL_PATH).replace("\\", "/") in doc_text
    assert str(DOWN_SQL_PATH).replace("\\", "/") in doc_text


def test_core_migration_docs_match_tables_relationships_and_indexes() -> None:
    doc_text = _read_text(DOC_PATH)
    up_sql_text = _read_text(UP_SQL_PATH)

    table_names = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\(", up_sql_text))
    index_names = set(re.findall(r"CREATE INDEX IF NOT EXISTS\s+(\w+)\s+ON", up_sql_text))

    for table_name in table_names:
        assert f"`{table_name}`" in doc_text
    for index_name in index_names:
        assert f"`{index_name}`" in doc_text

    assert "`funds.firm_id` -> `firms.firm_id`" in doc_text
    assert "`documents.fund_id` -> `funds.fund_id`" in doc_text
    assert "`(fund_id, file_hash, version_date)`" in doc_text


def test_core_migration_docs_match_rollback_order_and_pragmas() -> None:
    doc_text = _read_text(DOC_PATH)
    down_sql_text = _read_text(DOWN_SQL_PATH)

    rollback_order = re.findall(r"DROP TABLE IF EXISTS\s+(\w+);", down_sql_text)
    expected_order = ["documents", "funds", "firms"]
    assert rollback_order == expected_order

    for idx, table_name in enumerate(expected_order, start=1):
        assert f"{idx}. `{table_name}`" in doc_text

    assert "PRAGMA foreign_keys = OFF" in down_sql_text
    assert "PRAGMA foreign_keys = ON" in down_sql_text
    assert "PRAGMA foreign_keys = OFF" in doc_text
    assert "PRAGMA foreign_keys = ON" in doc_text


def test_core_schema_contract_includes_optional_field_extension_notes() -> None:
    core_schema_doc_text = _read_text(Path("docs/contracts/core_schema.md"))

    assert "Developer Notes: Optional Field Extension Strategy" in core_schema_doc_text
    assert "ALTER TABLE ... ADD COLUMN" in core_schema_doc_text
    assert "nullable first" in core_schema_doc_text
    assert "tolerant of `NULL`" in core_schema_doc_text
    assert "deterministic ordering" in core_schema_doc_text
    assert "repository tests" in core_schema_doc_text
