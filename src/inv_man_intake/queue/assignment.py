"""Analyst-first queue assignment and ops reassignment flow."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

from inv_man_intake.queue.sla import SlaFields, initialize_sla, mark_breach_if_due, reassign_sla

OwnerRole = Literal["analyst", "ops"]


class QueueAssignmentError(ValueError):
    """Raised when assignment ownership rules are violated."""


@dataclass(frozen=True)
class AssignmentEvent:
    """Immutable assignment audit event."""

    action: str
    at: datetime
    actor_id: str
    actor_role: OwnerRole
    note: str | None = None


@dataclass(frozen=True)
class QueueAssignmentRecord:
    """Queue ownership record with SLA fields and audit trail."""

    item_id: str
    owner_id: str
    owner_role: OwnerRole
    sla: SlaFields
    events: tuple[AssignmentEvent, ...]


def create_analyst_first_assignment(
    *,
    item_id: str,
    analyst_id: str,
    created_at: datetime | None = None,
) -> QueueAssignmentRecord:
    """Create queue ownership with analyst as default first owner."""

    if not item_id:
        raise QueueAssignmentError("item_id must be non-empty")
    if not analyst_id:
        raise QueueAssignmentError("analyst_id must be non-empty")

    created = created_at or _utc_now()
    sla = initialize_sla(created_at=created, assigned_at=created)
    first_event = AssignmentEvent(
        action="assigned_analyst",
        at=created,
        actor_id=analyst_id,
        actor_role="analyst",
        note="analyst-first default assignment",
    )
    return QueueAssignmentRecord(
        item_id=item_id,
        owner_id=analyst_id,
        owner_role="analyst",
        sla=sla,
        events=(first_event,),
    )


def reassign_to_ops_for_block(
    record: QueueAssignmentRecord,
    *,
    analyst_id: str,
    ops_id: str,
    reason: str,
    at: datetime | None = None,
) -> QueueAssignmentRecord:
    """Reassign from analyst to ops when operational blockers are flagged."""

    if record.owner_role != "analyst":
        raise QueueAssignmentError("record must be analyst-owned before reassignment to ops")
    if record.owner_id != analyst_id:
        raise QueueAssignmentError("only current analyst owner can request ops reassignment")
    if not ops_id:
        raise QueueAssignmentError("ops_id must be non-empty")
    if not reason:
        raise QueueAssignmentError("reason must be non-empty")

    reassigned_at = at or _utc_now()
    event = AssignmentEvent(
        action="reassigned_to_ops",
        at=reassigned_at,
        actor_id=analyst_id,
        actor_role="analyst",
        note=reason,
    )
    return replace(
        record,
        owner_id=ops_id,
        owner_role="ops",
        sla=reassign_sla(record.sla, assigned_at=reassigned_at),
        events=record.events + (event,),
    )


def update_sla_breach(
    record: QueueAssignmentRecord, *, now: datetime | None = None
) -> QueueAssignmentRecord:
    """Update breached_at when same-day SLA has been violated."""

    observed_at = now or _utc_now()
    return replace(record, sla=mark_breach_if_due(record.sla, now=observed_at))


def _utc_now() -> datetime:
    return datetime.now(UTC)
