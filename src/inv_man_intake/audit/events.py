"""Immutable audit event schema for queue actions and manual overrides."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass(frozen=True)
class QueueAuditEvent:
    """Append-only audit event for queue action traceability."""

    event_id: str
    item_id: str
    action: str
    actor_id: str
    actor_role: str
    at: str
    state_before: str | None = None
    state_after: str | None = None
    override_reason: str | None = None
    note: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


def create_queue_audit_event(
    *,
    item_id: str,
    action: str,
    actor_id: str,
    actor_role: str,
    state_before: str | None = None,
    state_after: str | None = None,
    override_reason: str | None = None,
    note: str | None = None,
    metadata: Mapping[str, str] | None = None,
    event_id: str | None = None,
    at: str | None = None,
) -> QueueAuditEvent:
    """Create a validated queue audit event."""

    if not item_id:
        raise ValueError("item_id must be non-empty")
    if not action:
        raise ValueError("action must be non-empty")
    if not actor_id:
        raise ValueError("actor_id must be non-empty")
    if not actor_role:
        raise ValueError("actor_role must be non-empty")

    resolved_event_id = event_id or f"audit_{uuid4().hex}"
    resolved_at = at or datetime.now(UTC).isoformat(timespec="seconds")
    resolved_metadata = {} if metadata is None else {str(k): str(v) for k, v in metadata.items()}
    return QueueAuditEvent(
        event_id=resolved_event_id,
        item_id=item_id,
        action=action,
        actor_id=actor_id,
        actor_role=actor_role,
        at=resolved_at,
        state_before=state_before,
        state_after=state_after,
        override_reason=override_reason,
        note=note,
        metadata=resolved_metadata,
    )
