"""Data models for package ingestion lifecycle state tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

IngestStatus = Literal["received", "processing", "completed", "escalated"]


@dataclass(frozen=True)
class IntakeFile:
    """One file in an inbound package."""

    file_name: str
    role: str
    source_ref: str | None = None
    document_id: str | None = None


@dataclass(frozen=True)
class IngestEvent:
    """Lifecycle event emitted on package state transitions."""

    package_id: str
    from_status: IngestStatus | None
    to_status: IngestStatus
    at: str
    note: str | None


@dataclass(frozen=True)
class IngestRecord:
    """Current lifecycle state for one package."""

    package_id: str
    firm_id: str
    fund_id: str
    status: IngestStatus
    file_count: int
    document_ids: tuple[str, ...]
    created_at: str
    updated_at: str
    note: str | None = None


@dataclass(frozen=True)
class EscalationPayload:
    """Escalation payload used by downstream validation queue."""

    package_id: str
    firm_id: str
    fund_id: str
    status: IngestStatus
    reason: str
    retry_attempted: bool
    fallback_tool: str | None
    file_count: int
    document_ids: tuple[str, ...]
    event_at: str
