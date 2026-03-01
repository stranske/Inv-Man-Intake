"""Tests for core repository behavior."""

from __future__ import annotations

import sqlite3

from inv_man_intake.data.models import Document, Firm, Fund
from inv_man_intake.data.repository import CoreRepository


def _repo() -> CoreRepository:
    conn = sqlite3.connect(":memory:")
    repo = CoreRepository(conn)
    repo.ensure_core_schema()
    return repo


def test_create_and_read_firm_fund_document() -> None:
    repo = _repo()
    repo.create_firm(
        Firm(
            firm_id="firm_1",
            legal_name="Alpha Capital",
            aliases_json=None,
            created_at="2026-03-01T09:00:00Z",
        )
    )
    repo.create_fund(
        Fund(
            fund_id="fund_1",
            firm_id="firm_1",
            fund_name="Alpha Market Neutral",
            strategy="market_neutral",
            asset_class="equity_market_neutral",
            created_at="2026-03-01T09:05:00Z",
        )
    )
    repo.create_document(
        Document(
            document_id="doc_1",
            fund_id="fund_1",
            file_name="alpha_deck.pdf",
            file_hash="hash_1",
            received_at="2026-03-01T09:10:00Z",
            version_date="2026-03-01",
            source_channel="email",
            created_at="2026-03-01T09:10:00Z",
        )
    )

    assert repo.get_firm("firm_1") is not None
    assert repo.get_fund("fund_1") is not None
    loaded_doc = repo.get_document("doc_1")
    assert loaded_doc is not None
    assert loaded_doc.file_name == "alpha_deck.pdf"


def test_update_firm_aliases() -> None:
    repo = _repo()
    repo.create_firm(
        Firm(
            firm_id="firm_2",
            legal_name="Beta Partners",
            aliases_json=None,
            created_at="2026-03-01T09:00:00Z",
        )
    )

    repo.update_firm_aliases("firm_2", '["Beta", "BPC"]')

    loaded = repo.get_firm("firm_2")
    assert loaded is not None
    assert loaded.aliases_json == '["Beta", "BPC"]'


def test_list_document_versions_sorted_by_version_date_then_received_at() -> None:
    repo = _repo()
    repo.create_firm(Firm("firm_1", "Alpha", None, "2026-03-01T09:00:00Z"))
    repo.create_fund(Fund("fund_1", "firm_1", "Alpha Fund", None, None, "2026-03-01T09:00:00Z"))

    repo.create_document(
        Document(
            "doc_2",
            "fund_1",
            "alpha_deck.pdf",
            "hash_2",
            "2026-03-02T09:00:00Z",
            "2026-03-02",
            "email",
            "2026-03-02T09:00:00Z",
        )
    )
    repo.create_document(
        Document(
            "doc_1",
            "fund_1",
            "alpha_deck.pdf",
            "hash_1",
            "2026-03-01T09:00:00Z",
            "2026-03-01",
            "email",
            "2026-03-01T09:00:00Z",
        )
    )

    versions = repo.list_document_versions("fund_1", "alpha_deck.pdf")
    assert [item.document_id for item in versions] == ["doc_1", "doc_2"]


def test_list_provenance_rows_returns_empty_when_table_missing() -> None:
    repo = _repo()
    assert repo.list_provenance_rows("doc_1") == ()


def test_list_provenance_rows_reads_when_table_exists() -> None:
    conn = sqlite3.connect(":memory:")
    repo = CoreRepository(conn)
    repo.ensure_core_schema()
    conn.execute(
        "CREATE TABLE extracted_fields (field_key TEXT, value TEXT, source_page INTEGER, document_id TEXT)"
    )
    conn.execute(
        "INSERT INTO extracted_fields (field_key, value, source_page, document_id) VALUES (?, ?, ?, ?)",
        ("terms.management_fee", "2%", 4, "doc_1"),
    )
    conn.commit()

    rows = repo.list_provenance_rows("doc_1")
    assert rows == (("terms.management_fee", "2%", 4),)
