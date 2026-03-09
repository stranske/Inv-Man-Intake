"""SLA field helpers for assignment lifecycle tracking."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time


@dataclass(frozen=True)
class SlaFields:
    """SLA timestamps persisted across queue ownership lifecycle."""

    created_at: datetime
    assigned_at: datetime
    due_at: datetime
    breached_at: datetime | None = None


def initialize_sla(*, created_at: datetime, assigned_at: datetime | None = None) -> SlaFields:
    """Initialize same-day SLA fields for new queue assignment."""

    _require_tz_aware(created_at=created_at)
    effective_assigned_at = assigned_at or created_at
    _require_tz_aware(assigned_at=effective_assigned_at)
    return SlaFields(
        created_at=created_at,
        assigned_at=effective_assigned_at,
        due_at=_same_day_due(effective_assigned_at),
        breached_at=None,
    )


def reassign_sla(sla: SlaFields, *, assigned_at: datetime) -> SlaFields:
    """Update assignment and due timestamps while preserving created/breach history."""

    _require_tz_aware(assigned_at=assigned_at)
    return replace(
        sla,
        assigned_at=assigned_at,
        due_at=_same_day_due(assigned_at),
    )


def mark_breach_if_due(sla: SlaFields, *, now: datetime) -> SlaFields:
    """Set breach timestamp when due time has passed and breach was not set."""

    _require_tz_aware(now=now)
    if sla.breached_at is not None:
        return sla
    if now <= sla.due_at:
        return sla
    return replace(sla, breached_at=now)


def _same_day_due(moment: datetime) -> datetime:
    return datetime.combine(moment.date(), time(23, 59, 59), tzinfo=moment.tzinfo)


def _require_tz_aware(**fields: datetime) -> None:
    for name, value in fields.items():
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
