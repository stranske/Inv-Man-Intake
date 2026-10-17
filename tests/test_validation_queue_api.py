"""Tests for validation queue API filter contracts and pagination."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from inv_man_intake.validation_queue_api import (
    ValidationQueueQuery,
    build_query_from_params,
    list_validation_queue,
)
from inv_man_intake.validation_queue_api import __all__ as queue_api_exports
from inv_man_intake.workflow_validation import (
    QUEUE_ARTIFACT_SCHEMA,
    ValidationQueueRow,
    ValidationWorkflowError,
    claim_for_analyst_triage,
    create_queue_item,
    load_validation_queue,
    load_validation_queue_rows,
    queue_replay_key,
    to_queue_row,
    transfer_owner,
    transition_state,
    write_validation_queue,
)


def _sample_rows() -> tuple[ValidationQueueRow, ...]:
    first = create_queue_item(
        item_id="queue-1",
        package_id="pkg-101",
        escalation_reason="confidence_below_threshold",
    )
    second = create_queue_item(
        item_id="queue-2",
        package_id="pkg-102",
        escalation_reason="policy_exception",
    )
    third = create_queue_item(
        item_id="queue-3",
        package_id="pkg-103",
        escalation_reason="conflicting_returns",
    )

    first = claim_for_analyst_triage(first, analyst_id="analyst-1")
    second = claim_for_analyst_triage(second, analyst_id="analyst-2")
    second = transition_state(
        second,
        actor_id="analyst-2",
        actor_role="analyst",
        to_state="awaiting_manager_response",
    )

    third = claim_for_analyst_triage(third, analyst_id="analyst-3")
    third = transfer_owner(
        third,
        actor_id="analyst-3",
        actor_role="analyst",
        new_owner_id="ops-1",
        new_owner_role="ops",
    )
    third = transition_state(
        third,
        actor_id="ops-1",
        actor_role="ops",
        to_state="ops_review",
    )

    return (to_queue_row(first), to_queue_row(second), to_queue_row(third))


def test_filters_by_state_and_owner_role() -> None:
    rows = _sample_rows()

    page = list_validation_queue(
        rows,
        query=ValidationQueueQuery(states=("ops_review",), owner_roles=("ops",)),
    )

    assert page.total == 1
    assert len(page.items) == 1
    assert page.items[0].item_id == "queue-3"


def test_filters_by_package_and_escalation_substring() -> None:
    rows = _sample_rows()

    page = list_validation_queue(
        rows,
        query=ValidationQueueQuery(
            package_id="pkg-101",
            escalation_reason_contains="threshold",
        ),
    )

    assert page.total == 1
    assert page.items[0].item_id == "queue-1"


def test_pagination_applies_after_sorting() -> None:
    rows = _sample_rows()

    page = list_validation_queue(
        rows,
        query=ValidationQueueQuery(sort_by="owner_id", sort_direction="asc", limit=1, offset=1),
    )

    assert page.total == 3
    assert len(page.items) == 1
    assert page.items[0].item_id in {"queue-2", "queue-3"}


def test_timestamp_filters_accept_z_suffix_and_naive_timestamps() -> None:
    rows = _sample_rows()
    rows = (
        replace(rows[0], updated_at="2026-03-07T10:00:00+00:00"),
        replace(rows[1], updated_at="2026-03-07T11:00:00+00:00"),
        replace(rows[2], updated_at="2026-03-07T12:00:00+00:00"),
    )

    page = list_validation_queue(
        rows,
        query=ValidationQueueQuery(
            updated_after="2026-03-07T11:30:00Z",
            updated_before="2026-03-07T12:30:00",
        ),
    )

    assert page.total == 1
    assert page.items[0].item_id == "queue-3"


def test_rejects_invalid_query_limits() -> None:
    rows = _sample_rows()

    with pytest.raises(ValueError, match="greater than zero"):
        list_validation_queue(rows, query=ValidationQueueQuery(limit=0))

    with pytest.raises(ValueError, match="less than or equal to 500"):
        list_validation_queue(rows, query=ValidationQueueQuery(limit=501))

    with pytest.raises(ValueError, match="greater than or equal to zero"):
        list_validation_queue(rows, query=ValidationQueueQuery(offset=-1))


def test_build_query_from_params_parses_lists_and_paging() -> None:
    query = build_query_from_params(
        {
            "state": "in_validation,ops_review",
            "owner_role": "analyst,ops",
            "owner_id": " analyst-1 ",
            "package_id": "pkg-101",
            "escalation_contains": "threshold",
            "limit": "10",
            "offset": "2",
            "sort_by": "state",
            "sort_direction": "asc",
        }
    )

    assert query.states == ("in_validation", "ops_review")
    assert query.owner_roles == ("analyst", "ops")
    assert query.owner_id == "analyst-1"
    assert query.limit == 10
    assert query.offset == 2
    assert query.sort_by == "state"
    assert query.sort_direction == "asc"


def test_build_query_rejects_invalid_state() -> None:
    with pytest.raises(ValueError, match="Invalid state"):
        build_query_from_params({"state": "unknown"})


def test_build_query_rejects_non_integer_paging_params() -> None:
    with pytest.raises(ValueError, match="limit must be an integer"):
        build_query_from_params({"limit": "five"})

    with pytest.raises(ValueError, match="offset must be an integer"):
        build_query_from_params({"offset": "start"})


def test_direct_query_validation_rejects_invalid_sort_and_state() -> None:
    rows = _sample_rows()

    with pytest.raises(ValueError, match="Invalid state"):
        list_validation_queue(rows, query=ValidationQueueQuery(states=("invalid",)))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid sort_by"):
        list_validation_queue(rows, query=ValidationQueueQuery(sort_by="age"))  # type: ignore[arg-type]


def test_consumer_ui_contract_exports() -> None:
    assert queue_api_exports == (
        "ValidationQueuePage",
        "ValidationQueueQuery",
        "build_query_from_params",
        "list_validation_queue",
    )


def test_queue_handoff_replay_and_claim_complete_preserve_events(tmp_path: Path) -> None:
    item = create_queue_item(
        item_id=queue_replay_key("pkg", "low_coverage"),
        package_id="pkg",
        escalation_reason="low_coverage",
    )
    file = tmp_path / "queue.json"
    write_validation_queue(file, [item, item])
    assert load_validation_queue(file) == (item,)
    claimed = claim_for_analyst_triage(load_validation_queue(file)[0], analyst_id="explicit-owner")
    completed = transition_state(
        claimed, actor_id="explicit-owner", actor_role="analyst", to_state="completed"
    )
    write_validation_queue(file, [completed])
    assert load_validation_queue(file) == (completed,)
    assert [event.action for event in load_validation_queue(file)[0].events] == [
        "claim",
        "state_transition",
    ]
    page = list_validation_queue(
        load_validation_queue_rows(file),
        query=ValidationQueueQuery(package_id="pkg", states=("completed",)),
    )
    assert page.total == 1 and page.items[0].owner_id == "explicit-owner"


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "invented"},
        {"owner_id": True},
        {"events": {}},
        {"created_at": "2026-01-01"},
        {"package_id": None},
        {"item_id": " "},
        {"escalation_reason": ""},
        {"owner_id": "analyst", "owner_role": None},
        {"owner_id": None, "owner_role": "analyst"},
        {"owner_id": "analyst", "owner_role": "manager"},
        {"owner_id": " ", "owner_role": "analyst"},
        {"owner_id": "analyst", "owner_role": "analyst"},
        {"state": "in_validation"},
        {"state": "completed"},
        {"created_at": "invalid"},
        {"updated_at": 123},
        {"updated_at": "2026-01-01T10:00:00"},
        {"created_at": "2026-01-02T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"},
        {"unexpected_field": "value"},
    ],
)
def test_queue_loader_rejects_malformed_typed_records(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    raw = asdict(
        create_queue_item(item_id="item", package_id="pkg", escalation_reason="low_coverage")
    )
    raw["events"] = []
    raw.update(changes)
    file = tmp_path / "queue.json"
    file.write_text(json.dumps({"schema_version": QUEUE_ARTIFACT_SCHEMA, "items": [raw]}))
    with pytest.raises(ValidationWorkflowError):
        load_validation_queue(file)


@pytest.mark.parametrize("duplicate", ["record", "item_id", "replay_key"])
def test_queue_loader_rejects_duplicate_identity(tmp_path: Path, duplicate: str) -> None:
    item = create_queue_item(item_id="item", package_id="pkg", escalation_reason="low_coverage")
    file = tmp_path / "queue.json"
    write_validation_queue(file, [item])
    payload = json.loads(file.read_text())
    second = dict(payload["items"][0])
    if duplicate == "item_id":
        second["package_id"] = "other-package"
    elif duplicate == "replay_key":
        second["item_id"] = "other-item"
    payload["items"].append(second)
    file.write_text(json.dumps(payload))
    with pytest.raises(ValidationWorkflowError, match="Duplicate"):
        load_validation_queue(file)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"items": []},
        {"schema_version": "unknown", "items": []},
        {"schema_version": QUEUE_ARTIFACT_SCHEMA, "items": {}},
        {"schema_version": QUEUE_ARTIFACT_SCHEMA, "items": [], "extra": True},
        {"schema_version": QUEUE_ARTIFACT_SCHEMA, "items": [{}]},
    ],
)
def test_queue_loader_rejects_malformed_schema(tmp_path: Path, payload: object) -> None:
    file = tmp_path / "queue.json"
    file.write_text(json.dumps(payload))
    with pytest.raises(ValidationWorkflowError):
        load_validation_queue(file)


def test_queue_replay_pair_encoding_has_no_delimiter_collision() -> None:
    assert queue_replay_key("a:b", "c") != queue_replay_key("a", "b:c")
    assert queue_replay_key("pkg", "reason") == queue_replay_key("pkg", "reason")


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "invented"},
        {"actor_id": " "},
        {"actor_role": "manager"},
        {"note": 42},
        {"at": "2026-01-01T10:00:00"},
        {"at": "invalid"},
        {"at": None},
        {"extra": True},
    ],
)
def test_queue_loader_rejects_malformed_events(tmp_path: Path, changes: dict[str, object]) -> None:
    item = claim_for_analyst_triage(
        create_queue_item(item_id="item", package_id="pkg", escalation_reason="low_coverage"),
        analyst_id="analyst",
    )
    raw = asdict(item)
    event = asdict(item.events[0])
    event.update(changes)
    raw["events"] = [event]
    file = tmp_path / "queue.json"
    file.write_text(json.dumps({"schema_version": QUEUE_ARTIFACT_SCHEMA, "items": [raw]}))
    with pytest.raises(ValidationWorkflowError):
        load_validation_queue(file)


@pytest.mark.parametrize("invalid", ["conflicting_replay", "duplicate_id", "unowned_completed"])
def test_queue_writer_rejects_invalid_records_without_overwriting(
    tmp_path: Path, invalid: str
) -> None:
    item = create_queue_item(item_id="item", package_id="pkg", escalation_reason="low_coverage")
    file = tmp_path / "queue.json"
    write_validation_queue(file, [item])
    original = file.read_bytes()
    if invalid == "conflicting_replay":
        records = [item, claim_for_analyst_triage(item, analyst_id="analyst")]
    elif invalid == "duplicate_id":
        records = [item, replace(item, package_id="other-package")]
    else:
        records = [replace(item, state="completed")]
    with pytest.raises(ValidationWorkflowError):
        write_validation_queue(file, records)
    assert file.read_bytes() == original
