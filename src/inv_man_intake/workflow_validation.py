"""Validation queue ownership rules and workflow state transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

ValidationState = Literal[
    "pending_triage",
    "in_validation",
    "awaiting_manager_response",
    "ops_review",
    "completed",
    "rejected",
]
OwnerRole = Literal["analyst", "ops"]

_TERMINAL_STATES: set[ValidationState] = {"completed", "rejected"}
_ALLOWED_TRANSITIONS: dict[ValidationState, set[ValidationState]] = {
    "pending_triage": {"in_validation"},
    "in_validation": {
        "awaiting_manager_response",
        "ops_review",
        "completed",
        "rejected",
    },
    "awaiting_manager_response": {"in_validation", "ops_review", "rejected"},
    "ops_review": {"in_validation", "completed", "rejected"},
    "completed": set(),
    "rejected": set(),
}


class ValidationWorkflowError(ValueError):
    """Raised when a queue ownership or transition rule is violated."""


@dataclass(frozen=True)
class QueueEvent:
    """Immutable audit event for queue item state and ownership changes."""

    action: str
    at: str
    actor_id: str
    actor_role: OwnerRole
    note: str | None = None


@dataclass(frozen=True)
class ValidationQueueItem:
    """Queue item tracked through analyst-first triage and validation states."""

    item_id: str
    package_id: str
    state: ValidationState
    owner_id: str | None
    owner_role: OwnerRole | None
    escalation_reason: str
    created_at: str
    updated_at: str
    events: tuple[QueueEvent, ...] = ()


@dataclass(frozen=True)
class ValidationQueueRow:
    """Dashboard row projection for analyst/ops triage views."""

    item_id: str
    package_id: str
    state: ValidationState
    owner_id: str | None
    owner_role: OwnerRole | None
    escalation_reason: str
    next_action: str
    updated_at: str


def create_queue_item(
    *, item_id: str, package_id: str, escalation_reason: str
) -> ValidationQueueItem:
    """Create an unowned queue item in pending triage state."""

    _require_non_empty(item_id=item_id, package_id=package_id, escalation_reason=escalation_reason)
    timestamp = _utc_now()
    return ValidationQueueItem(
        item_id=item_id,
        package_id=package_id,
        state="pending_triage",
        owner_id=None,
        owner_role=None,
        escalation_reason=escalation_reason,
        created_at=timestamp,
        updated_at=timestamp,
        events=(),
    )


def claim_for_analyst_triage(
    item: ValidationQueueItem, *, analyst_id: str, note: str | None = None
) -> ValidationQueueItem:
    """Claim a pending queue item for analyst first-touch triage."""

    if item.owner_id is not None:
        raise ValidationWorkflowError("Queue item already has an owner")
    if item.state != "pending_triage":
        raise ValidationWorkflowError("Only pending_triage items can be claimed")

    timestamp = _utc_now()
    event = QueueEvent(
        action="claim",
        at=timestamp,
        actor_id=analyst_id,
        actor_role="analyst",
        note=note,
    )
    return replace(
        item,
        state="in_validation",
        owner_id=analyst_id,
        owner_role="analyst",
        updated_at=timestamp,
        events=item.events + (event,),
    )


def transfer_owner(
    item: ValidationQueueItem,
    *,
    actor_id: str,
    actor_role: OwnerRole,
    new_owner_id: str,
    new_owner_role: OwnerRole,
    note: str | None = None,
) -> ValidationQueueItem:
    """Transfer queue ownership between analysts and ops."""

    if item.state in _TERMINAL_STATES:
        raise ValidationWorkflowError("Cannot transfer ownership for terminal queue items")
    if item.owner_id is None:
        raise ValidationWorkflowError("Queue item must be claimed before ownership transfer")
    if actor_id != item.owner_id and actor_role != "ops":
        raise ValidationWorkflowError("Only current owner or ops can transfer ownership")

    timestamp = _utc_now()
    event = QueueEvent(
        action="transfer",
        at=timestamp,
        actor_id=actor_id,
        actor_role=actor_role,
        note=note,
    )
    return replace(
        item,
        owner_id=new_owner_id,
        owner_role=new_owner_role,
        updated_at=timestamp,
        events=item.events + (event,),
    )


def transition_state(
    item: ValidationQueueItem,
    *,
    actor_id: str,
    actor_role: OwnerRole,
    to_state: ValidationState,
    note: str | None = None,
) -> ValidationQueueItem:
    """Move a queue item to a new state when transition rules are satisfied."""

    if item.state == to_state:
        return item
    if item.owner_id is None:
        raise ValidationWorkflowError("Queue item must be claimed before state transitions")
    if item.owner_id != actor_id and actor_role != "ops":
        raise ValidationWorkflowError("Only current owner or ops can transition state")

    allowed = _ALLOWED_TRANSITIONS[item.state]
    if to_state not in allowed:
        raise ValidationWorkflowError(f"Invalid transition: {item.state} -> {to_state}")

    timestamp = _utc_now()
    event = QueueEvent(
        action="state_transition",
        at=timestamp,
        actor_id=actor_id,
        actor_role=actor_role,
        note=note,
    )
    return replace(
        item,
        state=to_state,
        updated_at=timestamp,
        events=item.events + (event,),
    )


def to_queue_row(item: ValidationQueueItem) -> ValidationQueueRow:
    """Project a queue item to a triage dashboard row contract."""

    return ValidationQueueRow(
        item_id=item.item_id,
        package_id=item.package_id,
        state=item.state,
        owner_id=item.owner_id,
        owner_role=item.owner_role,
        escalation_reason=item.escalation_reason,
        next_action=_next_action_for_state(item.state),
        updated_at=item.updated_at,
    )


def _next_action_for_state(state: ValidationState) -> str:
    if state == "pending_triage":
        return "Claim by analyst"
    if state == "in_validation":
        return "Review extracted fields"
    if state == "awaiting_manager_response":
        return "Collect manager clarification"
    if state == "ops_review":
        return "Ops policy decision"
    if state == "completed":
        return "No action"
    return "No action"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _require_non_empty(*, item_id: str, package_id: str, escalation_reason: str) -> None:
    if not item_id:
        raise ValidationWorkflowError("item_id must be non-empty")
    if not package_id:
        raise ValidationWorkflowError("package_id must be non-empty")
    if not escalation_reason:
        raise ValidationWorkflowError("escalation_reason must be non-empty")
