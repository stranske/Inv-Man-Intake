"""Validation queue state machine and transition guard rails."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

QueueState = Literal["new", "assigned", "in_review", "resolved", "blocked"]
ActorRole = Literal["analyst", "ops", "system"]

_ALLOWED_TRANSITIONS: dict[QueueState, set[QueueState]] = {
    "new": {"assigned"},
    "assigned": {"in_review", "blocked"},
    "in_review": {"resolved", "blocked", "assigned"},
    "blocked": {"assigned", "in_review"},
    "resolved": set(),
}
_VALID_ACTOR_ROLES: set[ActorRole] = {"analyst", "ops", "system"}


class QueueTransitionError(ValueError):
    """Raised when a requested queue transition is not allowed."""


class QueuePermissionError(ValueError):
    """Raised when actor permissions do not permit the action."""


@dataclass(frozen=True)
class QueueItem:
    """Queue item tracked through state and assignee changes."""

    item_id: str
    state: QueueState
    assignee_id: str | None
    created_at: str
    updated_at: str


def create_queue_item(*, item_id: str) -> QueueItem:
    """Create a queue item in the initial `new` state."""

    if not item_id:
        raise QueueTransitionError("item_id must be non-empty")
    timestamp = _utc_now()
    return QueueItem(
        item_id=item_id,
        state="new",
        assignee_id=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def assign_item(
    item: QueueItem,
    *,
    actor_id: str,
    actor_role: ActorRole,
    assignee_id: str,
) -> QueueItem:
    """Assign or reassign ownership and move item into `assigned` state."""

    if not actor_id or not actor_id.strip():
        raise QueuePermissionError("actor_id must be non-empty")
    if actor_role not in _VALID_ACTOR_ROLES:
        raise QueuePermissionError(f"invalid actor_role: {actor_role}")
    if not assignee_id or not assignee_id.strip():
        raise QueuePermissionError("assignee_id must be non-empty")

    if item.state == "new":
        if actor_role not in {"analyst", "ops"}:
            raise QueuePermissionError("only analyst or ops can assign new items")
    elif item.state in {"assigned", "in_review", "blocked"}:
        if actor_role != "ops":
            raise QueuePermissionError("only ops can reassign active items")
    else:
        raise QueueTransitionError(f"cannot assign item from terminal state: {item.state}")

    timestamp = _utc_now()
    return replace(item, state="assigned", assignee_id=assignee_id, updated_at=timestamp)


def transition_item(
    item: QueueItem,
    *,
    actor_id: str,
    actor_role: ActorRole,
    to_state: QueueState,
) -> QueueItem:
    """Transition to a new state when matrix and permission rules allow it."""

    if not actor_id or not actor_id.strip():
        raise QueuePermissionError("actor_id must be non-empty")
    if actor_role not in _VALID_ACTOR_ROLES:
        raise QueuePermissionError(f"invalid actor_role: {actor_role}")
    if to_state == item.state:
        return item

    allowed = _ALLOWED_TRANSITIONS[item.state]
    if to_state not in allowed:
        raise QueueTransitionError(f"invalid transition: {item.state} -> {to_state}")

    _check_transition_permission(
        item=item, actor_id=actor_id, actor_role=actor_role, to_state=to_state
    )
    timestamp = _utc_now()
    return replace(item, state=to_state, updated_at=timestamp)


def _check_transition_permission(
    *,
    item: QueueItem,
    actor_id: str,
    actor_role: ActorRole,
    to_state: QueueState,
) -> None:
    if to_state == "assigned":
        if actor_role != "ops":
            raise QueuePermissionError("only ops can transition item to assigned")
        return

    if item.assignee_id is None:
        raise QueuePermissionError("assignee_id must be set before workflow transitions")

    is_assignee = actor_id == item.assignee_id
    if actor_role not in {"ops", "system"} and not is_assignee:
        raise QueuePermissionError("only assignee or ops can transition this item")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
