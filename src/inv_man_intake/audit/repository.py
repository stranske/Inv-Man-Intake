"""Append-only in-memory repository for queue audit events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from .events import QueueAuditEvent, create_queue_audit_event


@dataclass(frozen=True)
class QueueAuditRepository:
    """Immutable append-only event store for queue audit trails."""

    _events: tuple[QueueAuditEvent, ...] = ()

    def append(self, event: QueueAuditEvent) -> QueueAuditRepository:
        """Append one event and return a new repository instance."""
        try:
            event_at = datetime.fromisoformat(event.at)
        except ValueError as exc:
            raise ValueError("event.at must be a valid ISO-8601 datetime") from exc
        if self._events and (event_at < datetime.fromisoformat(self._events[-1].at)):
            raise ValueError("audit events must be appended in non-decreasing timestamp order")
        return QueueAuditRepository(_events=self._events + (event,))

    def append_queue_action(
        self,
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
    ) -> QueueAuditRepository:
        """Create and append a queue audit event in one call."""
        event = create_queue_audit_event(
            item_id=item_id,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            state_before=state_before,
            state_after=state_after,
            override_reason=override_reason,
            note=note,
            metadata=metadata,
            event_id=event_id,
            at=at,
        )
        return self.append(event)

    def extend(self, events: Iterable[QueueAuditEvent]) -> QueueAuditRepository:
        """Append multiple events in sequence and return a new repository."""
        repo = self
        for event in events:
            repo = repo.append(event)
        return repo

    def list_for_item(self, item_id: str) -> tuple[QueueAuditEvent, ...]:
        """Return item-level trail in deterministic append order."""
        return tuple(event for event in self._events if event.item_id == item_id)

    def all_events(self) -> tuple[QueueAuditEvent, ...]:
        """Return all events in append order."""
        return self._events
