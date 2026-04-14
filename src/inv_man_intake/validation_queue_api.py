"""Validation queue query contracts and filter endpoint helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypeGuard

from .workflow_validation import OwnerRole, ValidationQueueRow, ValidationState

QueueSortBy = Literal["updated_at", "state", "owner_id"]
QueueSortDirection = Literal["asc", "desc"]

_ALLOWED_STATES: tuple[ValidationState, ...] = (
    "pending_triage",
    "in_validation",
    "awaiting_manager_response",
    "ops_review",
    "completed",
    "rejected",
)
_ALLOWED_OWNER_ROLES: tuple[OwnerRole, ...] = ("analyst", "ops")


@dataclass(frozen=True)
class ValidationQueueQuery:
    """Query contract for queue-list filters and ordering."""

    states: tuple[ValidationState, ...] = ()
    owner_roles: tuple[OwnerRole, ...] = ()
    owner_id: str | None = None
    package_id: str | None = None
    escalation_reason_contains: str | None = None
    updated_after: str | None = None
    updated_before: str | None = None
    limit: int = 50
    offset: int = 0
    sort_by: QueueSortBy = "updated_at"
    sort_direction: QueueSortDirection = "desc"


@dataclass(frozen=True)
class ValidationQueuePage:
    """Paginated result contract for queue row responses."""

    items: tuple[ValidationQueueRow, ...]
    total: int
    limit: int
    offset: int


def list_validation_queue(
    rows: Iterable[ValidationQueueRow], *, query: ValidationQueueQuery
) -> ValidationQueuePage:
    """Apply filter/query contract and return a paginated queue response."""

    _validate_query(query)

    filtered = [row for row in rows if _matches_query(row, query)]
    ordered = sorted(
        filtered,
        key=lambda row: _sort_key(row, query.sort_by),
        reverse=query.sort_direction == "desc",
    )
    page_items = tuple(ordered[query.offset : query.offset + query.limit])
    return ValidationQueuePage(
        items=page_items,
        total=len(ordered),
        limit=query.limit,
        offset=query.offset,
    )


def build_query_from_params(params: Mapping[str, str]) -> ValidationQueueQuery:
    """Build a normalized query contract from endpoint string params."""

    state_tokens = _split_csv(params.get("state"))
    states = tuple(_parse_state(token) for token in state_tokens)

    role_tokens = _split_csv(params.get("owner_role"))
    owner_roles = tuple(_parse_owner_role(token) for token in role_tokens)

    limit = _parse_int_param(params, "limit", 50)
    offset = _parse_int_param(params, "offset", 0)

    sort_by = _parse_sort_by(params.get("sort_by", "updated_at"))
    sort_direction = _parse_sort_direction(params.get("sort_direction", "desc"))

    return ValidationQueueQuery(
        states=states,
        owner_roles=owner_roles,
        owner_id=_optional_trim(params.get("owner_id")),
        package_id=_optional_trim(params.get("package_id")),
        escalation_reason_contains=_optional_trim(params.get("escalation_contains")),
        updated_after=_optional_trim(params.get("updated_after")),
        updated_before=_optional_trim(params.get("updated_before")),
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )


def _validate_query(query: ValidationQueueQuery) -> None:
    for state in query.states:
        _parse_state(state)
    for owner_role in query.owner_roles:
        _parse_owner_role(owner_role)
    _parse_sort_by(query.sort_by)
    _parse_sort_direction(query.sort_direction)

    if query.limit <= 0:
        raise ValueError("limit must be greater than zero")
    if query.limit > 500:
        raise ValueError("limit must be less than or equal to 500")
    if query.offset < 0:
        raise ValueError("offset must be greater than or equal to zero")

    if query.updated_after is not None:
        _parse_iso(query.updated_after)
    if query.updated_before is not None:
        _parse_iso(query.updated_before)


def _matches_query(row: ValidationQueueRow, query: ValidationQueueQuery) -> bool:
    if query.states and row.state not in query.states:
        return False
    if query.owner_roles and row.owner_role not in query.owner_roles:
        return False
    if query.owner_id is not None and row.owner_id != query.owner_id:
        return False
    if query.package_id is not None and row.package_id != query.package_id:
        return False

    if (
        query.escalation_reason_contains is not None
        and query.escalation_reason_contains.casefold() not in row.escalation_reason.casefold()
    ):
        return False

    if query.updated_after is not None and _parse_iso(row.updated_at) < _parse_iso(
        query.updated_after
    ):
        return False
    return not (
        query.updated_before is not None
        and _parse_iso(row.updated_at) > _parse_iso(query.updated_before)
    )


def _sort_key(row: ValidationQueueRow, sort_by: QueueSortBy) -> tuple[object, ...]:
    if sort_by == "updated_at":
        return (_parse_iso(row.updated_at), row.item_id)
    if sort_by == "state":
        return (row.state, row.item_id)
    owner = row.owner_id or ""
    return (owner, row.item_id)


def _parse_iso(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid ISO timestamp: {value}") from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_int_param(params: Mapping[str, str], name: str, default: int) -> int:
    raw = params.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _split_csv(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    parts = [part.strip() for part in value.split(",")]
    return tuple(part for part in parts if part)


def _optional_trim(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def _is_validation_state(value: str) -> TypeGuard[ValidationState]:
    return value in _ALLOWED_STATES


def _is_owner_role(value: str) -> TypeGuard[OwnerRole]:
    return value in _ALLOWED_OWNER_ROLES


def _parse_state(value: str) -> ValidationState:
    if not _is_validation_state(value):
        raise ValueError(f"Invalid state: {value}")
    return value


def _parse_owner_role(value: str) -> OwnerRole:
    if not _is_owner_role(value):
        raise ValueError(f"Invalid owner role: {value}")
    return value


def _parse_sort_by(value: str) -> QueueSortBy:
    if value not in {"updated_at", "state", "owner_id"}:
        raise ValueError(f"Invalid sort_by: {value}")
    return value  # type: ignore[return-value]


def _parse_sort_direction(value: str) -> QueueSortDirection:
    if value not in {"asc", "desc"}:
        raise ValueError(f"Invalid sort_direction: {value}")
    return value  # type: ignore[return-value]
