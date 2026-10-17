"""Validation queue ownership rules and workflow state transitions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args

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

    if not analyst_id:
        raise ValidationWorkflowError("analyst_id must be non-empty")
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

    if not actor_id:
        raise ValidationWorkflowError("actor_id must be non-empty")
    if not new_owner_id:
        raise ValidationWorkflowError("new_owner_id must be non-empty")
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
    if not actor_id:
        raise ValidationWorkflowError("actor_id must be non-empty")
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
    if state == "rejected":
        return "No further action"
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


QUEUE_ARTIFACT_SCHEMA = "validation-queue/v1"


def queue_replay_key(package_id: str, escalation_reason: str) -> str:
    """Stable identity across run IDs and replays; pair encoding avoids delimiter collisions."""
    _require_non_empty(item_id="replay", package_id=package_id, escalation_reason=escalation_reason)
    key = json.dumps([package_id, escalation_reason], ensure_ascii=False, separators=(",", ":"))
    return "validation:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def write_validation_queue(path: Path, items: Iterable[ValidationQueueItem]) -> None:
    """Write a local versioned handoff, retaining ownership and the complete event history."""
    unique: dict[tuple[str, str], ValidationQueueItem] = {}
    for item in items:
        key = (item.package_id, item.escalation_reason)
        if key in unique and unique[key] != item:
            raise ValidationWorkflowError("Conflicting queue records for the same replay key")
        unique[key] = item
    payload = {
        "schema_version": QUEUE_ARTIFACT_SCHEMA,
        "items": [
            {**asdict(unique[key]), "events": [asdict(event) for event in unique[key].events]}
            for key in sorted(unique)
        ],
    }
    # Use the same decoder before publication, so the writer cannot create an invalid handoff.
    _decode_validation_queue(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_validation_queue(path: Path) -> tuple[ValidationQueueItem, ...]:
    """Reload typed records/events for the existing claim/transfer/complete functions."""
    return _decode_validation_queue(json.loads(path.read_text(encoding="utf-8")))


def load_validation_queue_rows(path: Path) -> tuple[ValidationQueueRow, ...]:
    return tuple(to_queue_row(item) for item in load_validation_queue(path))


def _decode_validation_queue(payload: object) -> tuple[ValidationQueueItem, ...]:
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "items"}:
        raise ValidationWorkflowError("Invalid validation queue artifact object")
    if payload["schema_version"] != QUEUE_ARTIFACT_SCHEMA or not isinstance(payload["items"], list):
        raise ValidationWorkflowError("Unsupported validation queue schema or items")
    items = []
    keys: set[tuple[str, str]] = set()
    ids: set[str] = set()
    fields = set(ValidationQueueItem.__dataclass_fields__)
    event_fields = set(QueueEvent.__dataclass_fields__)
    for raw in payload["items"]:
        if not isinstance(raw, dict) or set(raw) != fields:
            raise ValidationWorkflowError("Invalid queue item fields")
        for key in ("item_id", "package_id", "escalation_reason", "created_at", "updated_at"):
            if not isinstance(raw[key], str) or not raw[key].strip():
                raise ValidationWorkflowError(f"Queue item {key} must be a non-empty string")
        if raw["state"] not in get_args(ValidationState):
            raise ValidationWorkflowError("Invalid queue state")
        if raw["owner_role"] not in (None, *get_args(OwnerRole)):
            raise ValidationWorkflowError("Invalid queue owner role")
        owner = raw["owner_id"]
        if owner is not None and (not isinstance(owner, str) or not owner.strip()):
            raise ValidationWorkflowError("Invalid queue owner identity")
        if (owner is None) != (raw["owner_role"] is None):
            raise ValidationWorkflowError("Queue owner identity and role must agree")
        if raw["state"] == "pending_triage" and owner is not None:
            raise ValidationWorkflowError("Pending queue item must be unowned")
        if raw["state"] != "pending_triage" and owner is None:
            raise ValidationWorkflowError("Non-pending queue item must have an owner")
        created_at = _queue_timestamp(raw["created_at"])
        updated_at = _queue_timestamp(raw["updated_at"])
        if updated_at < created_at:
            raise ValidationWorkflowError("Queue timestamps are out of order")
        if not isinstance(raw["events"], list):
            raise ValidationWorkflowError("Queue events must be a list")
        events = []
        previous_at = created_at
        for event in raw["events"]:
            if not isinstance(event, dict) or set(event) != event_fields:
                raise ValidationWorkflowError("Invalid queue event fields")
            if event["action"] not in ("claim", "transfer", "state_transition"):
                raise ValidationWorkflowError("Invalid queue event action")
            if not isinstance(event["actor_id"], str) or not event["actor_id"].strip():
                raise ValidationWorkflowError("Invalid queue event actor")
            if event["actor_role"] not in get_args(OwnerRole):
                raise ValidationWorkflowError("Invalid queue event actor role")
            if event["note"] is not None and not isinstance(event["note"], str):
                raise ValidationWorkflowError("Invalid queue event note")
            event_at = _queue_timestamp(event["at"])
            if not previous_at <= event_at <= updated_at:
                raise ValidationWorkflowError("Queue event timestamps are out of order or bounds")
            previous_at = event_at
            events.append(QueueEvent(**event))
        replay_key = (raw["package_id"], raw["escalation_reason"])
        if replay_key in keys or raw["item_id"] in ids:
            raise ValidationWorkflowError("Duplicate queue replay key or item identity")
        keys.add(replay_key)
        ids.add(raw["item_id"])
        items.append(ValidationQueueItem(**{**raw, "events": tuple(events)}))
    return tuple(items)


def _queue_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValidationWorkflowError("Queue timestamp must be an ISO UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationWorkflowError("Invalid queue timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationWorkflowError("Queue timestamp requires a timezone")
    return parsed.astimezone(UTC)
