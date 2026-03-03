"""Core data models for the firm -> fund -> document hierarchy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Firm:
    """Firm-level entity for manager organizations."""

    firm_id: str
    legal_name: str
    aliases_json: str | None
    created_at: str


@dataclass(frozen=True)
class Fund:
    """Fund/vehicle entity linked to a firm."""

    fund_id: str
    firm_id: str
    fund_name: str
    strategy: str | None
    asset_class: str | None
    created_at: str


@dataclass(frozen=True)
class Document:
    """Inbound document entity linked to a fund."""

    document_id: str
    fund_id: str
    file_name: str
    file_hash: str
    received_at: str
    version_date: str
    source_channel: str
    created_at: str
