"""Tests for validation queue API filter contracts and pagination."""

from __future__ import annotations

import pytest

from inv_man_intake.validation_queue_api import (
    ValidationQueueQuery,
    build_query_from_params,
    list_validation_queue,
)
from inv_man_intake.workflow_validation import (
    claim_for_analyst_triage,
    create_queue_item,
    to_queue_row,
    transfer_owner,
    transition_state,
)


def _sample_rows() -> tuple:
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
