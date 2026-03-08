"""Tests for core repository behavior."""

from __future__ import annotations

import sqlite3

import pytest

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

    repo.update_firm_aliases("firm_2", None)
    loaded = repo.get_firm("firm_2")
    assert loaded is not None
    assert loaded.aliases_json is None


def test_update_firm_aliases_unknown_firm_raises() -> None:
    repo = _repo()
    with pytest.raises(KeyError, match="unknown firm_id=missing"):
        repo.update_firm_aliases("missing", '["X"]')


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


def test_list_document_versions_uses_document_id_tie_breaker() -> None:
    repo = _repo()
    repo.create_firm(Firm("firm_1", "Alpha", None, "2026-03-01T09:00:00Z"))
    repo.create_fund(Fund("fund_1", "firm_1", "Alpha Fund", None, None, "2026-03-01T09:00:00Z"))

    repo.create_document(
        Document(
            "doc_b",
            "fund_1",
            "same.pdf",
            "hash_b",
            "2026-03-02T09:00:00Z",
            "2026-03-02",
            "email",
            "2026-03-02T09:00:00Z",
        )
    )
    repo.create_document(
        Document(
            "doc_a",
            "fund_1",
            "same.pdf",
            "hash_a",
            "2026-03-02T09:00:00Z",
            "2026-03-02",
            "email",
            "2026-03-02T09:00:00Z",
        )
    )

    versions = repo.list_document_versions("fund_1", "same.pdf")
    assert [item.document_id for item in versions] == ["doc_a", "doc_b"]


def test_update_fund_and_document_round_trip() -> None:
    repo = _repo()
    repo.create_firm(Firm("firm_1", "Alpha", None, "2026-03-01T09:00:00Z"))
    repo.create_firm(Firm("firm_2", "Beta", None, "2026-03-01T09:00:00Z"))
    repo.create_fund(Fund("fund_1", "firm_1", "Alpha Fund", None, None, "2026-03-01T09:00:00Z"))
    repo.create_document(
        Document(
            "doc_1",
            "fund_1",
            "alpha.pdf",
            "hash_1",
            "2026-03-01T09:10:00Z",
            "2026-03-01",
            "email",
            "2026-03-01T09:10:00Z",
        )
    )

    repo.update_fund(
        Fund(
            "fund_1",
            "firm_2",
            "Renamed Fund",
            "market_neutral",
            "equity_market_neutral",
            "2026-03-01T09:00:00Z",
        )
    )
    updated_fund = repo.get_fund("fund_1")
    assert updated_fund is not None
    assert updated_fund.firm_id == "firm_2"
    assert updated_fund.fund_name == "Renamed Fund"

    repo.update_document(
        Document(
            "doc_1",
            "fund_1",
            "alpha-v2.pdf",
            "hash_2",
            "2026-03-02T09:10:00Z",
            "2026-03-02",
            "portal",
            "2026-03-01T09:10:00Z",
        )
    )
    updated_doc = repo.get_document("doc_1")
    assert updated_doc is not None
    assert updated_doc.file_name == "alpha-v2.pdf"
    assert updated_doc.file_hash == "hash_2"
    assert updated_doc.source_channel == "portal"


def test_update_unknown_fund_or_document_raises() -> None:
    repo = _repo()
    with pytest.raises(KeyError, match="unknown fund_id=fund_missing"):
        repo.update_fund(Fund("fund_missing", "firm_1", "X", None, None, "2026-03-01T09:00:00Z"))

    with pytest.raises(KeyError, match="unknown document_id=doc_missing"):
        repo.update_document(
            Document(
                "doc_missing",
                "fund_1",
                "x.pdf",
                "hash",
                "2026-03-01T09:10:00Z",
                "2026-03-01",
                "email",
                "2026-03-01T09:10:00Z",
            )
        )


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
