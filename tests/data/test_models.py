"""Tests for core data model dataclasses."""

from inv_man_intake.data.models import Document, Firm, Fund


def test_firm_model_fields() -> None:
    firm = Firm(
        firm_id="firm_1",
        legal_name="Alpha Capital",
        aliases_json='["Alpha"]',
        created_at="2026-03-01T09:00:00Z",
    )

    assert firm.firm_id == "firm_1"
    assert firm.legal_name == "Alpha Capital"


def test_fund_model_fields() -> None:
    fund = Fund(
        fund_id="fund_1",
        firm_id="firm_1",
        fund_name="Alpha Market Neutral",
        strategy="market_neutral",
        asset_class="equity_market_neutral",
        created_at="2026-03-01T09:00:00Z",
    )

    assert fund.fund_id == "fund_1"
    assert fund.firm_id == "firm_1"


def test_document_model_fields() -> None:
    document = Document(
        document_id="doc_1",
        fund_id="fund_1",
        file_name="alpha_deck.pdf",
        file_hash="hash-1",
        received_at="2026-03-01T09:00:00Z",
        version_date="2026-03-01",
        source_channel="email",
        created_at="2026-03-01T09:00:00Z",
    )

    assert document.document_id == "doc_1"
    assert document.fund_id == "fund_1"
    assert document.file_name.endswith(".pdf")
