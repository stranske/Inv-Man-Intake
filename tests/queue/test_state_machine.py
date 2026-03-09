"""Tests for queue state machine transitions and permission guards."""

from __future__ import annotations

from typing import Literal

import pytest

from inv_man_intake.queue.state_machine import (
    QueuePermissionError,
    QueueTransitionError,
    assign_item,
    create_queue_item,
    transition_item,
)


def test_create_queue_item_defaults_to_new_and_unassigned() -> None:
    item = create_queue_item(item_id="queue-1")

    assert item.state == "new"
    assert item.assignee_id is None
    assert item.created_at == item.updated_at


@pytest.mark.parametrize("invalid_item_id", [" queue-1", "queue-1 ", "\tqueue-1\t"])
def test_create_queue_item_rejects_surrounding_whitespace(invalid_item_id: str) -> None:
    with pytest.raises(
        QueueTransitionError, match="item_id must not include surrounding whitespace"
    ):
        create_queue_item(item_id=invalid_item_id)


@pytest.mark.parametrize(
    ("role", "assignee"),
    [
        ("analyst", "analyst-1"),
        ("ops", "analyst-2"),
    ],
)
def test_assign_new_item_allows_analyst_or_ops(
    role: Literal["analyst", "ops"], assignee: str
) -> None:
    item = create_queue_item(item_id="queue-2")

    assigned = assign_item(item, actor_id="actor-1", actor_role=role, assignee_id=assignee)

    assert assigned.state == "assigned"
    assert assigned.assignee_id == assignee


def test_assign_new_item_rejects_system_actor() -> None:
    item = create_queue_item(item_id="queue-3")

    with pytest.raises(QueuePermissionError, match="only analyst or ops can assign new items"):
        assign_item(item, actor_id="svc-1", actor_role="system", assignee_id="analyst-1")


def test_assign_rejects_invalid_actor_role() -> None:
    item = create_queue_item(item_id="queue-3-invalid-role")

    with pytest.raises(QueuePermissionError, match="invalid actor_role: manager"):
        assign_item(  # type: ignore[arg-type]
            item, actor_id="mgr-1", actor_role="manager", assignee_id="analyst-1"
        )


@pytest.mark.parametrize("blank_actor_id", ["", " ", "   "])
def test_assign_rejects_blank_actor_id(blank_actor_id: str) -> None:
    item = create_queue_item(item_id="queue-3-blank-actor")

    with pytest.raises(QueuePermissionError, match="actor_id must be non-empty"):
        assign_item(item, actor_id=blank_actor_id, actor_role="analyst", assignee_id="analyst-1")


@pytest.mark.parametrize("actor_id", [" analyst-1", "analyst-1 "])
def test_assign_rejects_actor_id_with_surrounding_whitespace(actor_id: str) -> None:
    item = create_queue_item(item_id="queue-3-whitespace-actor")

    with pytest.raises(
        QueuePermissionError, match="actor_id must not include surrounding whitespace"
    ):
        assign_item(item, actor_id=actor_id, actor_role="analyst", assignee_id="analyst-1")


@pytest.mark.parametrize("blank_assignee_id", ["", " ", "   "])
def test_assign_rejects_blank_assignee_id(blank_assignee_id: str) -> None:
    item = create_queue_item(item_id="queue-3-blank-assignee")

    with pytest.raises(QueuePermissionError, match="assignee_id must be non-empty"):
        assign_item(item, actor_id="analyst-1", actor_role="analyst", assignee_id=blank_assignee_id)


@pytest.mark.parametrize("assignee_id", [" analyst-1", "analyst-1 "])
def test_assign_rejects_assignee_id_with_surrounding_whitespace(assignee_id: str) -> None:
    item = create_queue_item(item_id="queue-3-whitespace-assignee")

    with pytest.raises(
        QueuePermissionError, match="assignee_id must not include surrounding whitespace"
    ):
        assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id=assignee_id)


def test_transition_matrix_accepts_valid_paths() -> None:
    item = create_queue_item(item_id="queue-4")
    item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")
    item = transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="in_review")
    item = transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="blocked")
    item = transition_item(item, actor_id="ops-1", actor_role="ops", to_state="assigned")
    item = transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="in_review")
    item = transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="resolved")

    assert item.state == "resolved"


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        ("new", "in_review"),
        ("new", "blocked"),
        ("assigned", "resolved"),
        ("blocked", "resolved"),
        ("resolved", "assigned"),
        ("resolved", "in_review"),
    ],
)
def test_transition_matrix_rejects_invalid_transitions(from_state: str, to_state: str) -> None:
    item = create_queue_item(item_id=f"queue-{from_state}-{to_state}")
    if from_state != "new":
        item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")
    if from_state == "in_review":
        item = transition_item(
            item, actor_id="analyst-1", actor_role="analyst", to_state="in_review"
        )
    if from_state == "blocked":
        item = transition_item(
            item, actor_id="analyst-1", actor_role="analyst", to_state="in_review"
        )
        item = transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="blocked")
    if from_state == "resolved":
        item = transition_item(
            item, actor_id="analyst-1", actor_role="analyst", to_state="in_review"
        )
        item = transition_item(
            item, actor_id="analyst-1", actor_role="analyst", to_state="resolved"
        )

    with pytest.raises(
        QueueTransitionError, match=f"invalid transition: {from_state} -> {to_state}"
    ):
        transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state=to_state)  # type: ignore[arg-type]


def test_transition_rejects_non_assignee_non_ops_actor() -> None:
    item = create_queue_item(item_id="queue-5")
    item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")

    with pytest.raises(QueuePermissionError, match="only assignee or ops can transition this item"):
        transition_item(item, actor_id="analyst-2", actor_role="analyst", to_state="in_review")


def test_transition_to_assigned_requires_ops_role() -> None:
    item = create_queue_item(item_id="queue-6")
    item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")
    item = transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="in_review")

    with pytest.raises(QueuePermissionError, match="only ops can transition item to assigned"):
        transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="assigned")


def test_transition_rejects_invalid_actor_role() -> None:
    item = create_queue_item(item_id="queue-6-invalid-role")
    item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")

    with pytest.raises(QueuePermissionError, match="invalid actor_role: manager"):
        transition_item(  # type: ignore[arg-type]
            item, actor_id="mgr-1", actor_role="manager", to_state="in_review"
        )


@pytest.mark.parametrize("blank_actor_id", ["", " ", "   "])
def test_transition_rejects_blank_actor_id(blank_actor_id: str) -> None:
    item = create_queue_item(item_id="queue-6-blank-transition-actor")
    item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")

    with pytest.raises(QueuePermissionError, match="actor_id must be non-empty"):
        transition_item(item, actor_id=blank_actor_id, actor_role="analyst", to_state="in_review")


@pytest.mark.parametrize("actor_id", [" analyst-1", "analyst-1 "])
def test_transition_rejects_actor_id_with_surrounding_whitespace(actor_id: str) -> None:
    item = create_queue_item(item_id="queue-6-whitespace-transition-actor")
    item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")

    with pytest.raises(
        QueuePermissionError, match="actor_id must not include surrounding whitespace"
    ):
        transition_item(item, actor_id=actor_id, actor_role="analyst", to_state="in_review")


def test_assign_reassignment_requires_ops_for_active_items() -> None:
    item = create_queue_item(item_id="queue-7")
    item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")

    with pytest.raises(QueuePermissionError, match="only ops can reassign active items"):
        assign_item(item, actor_id="analyst-1", actor_role="analyst", assignee_id="analyst-2")


def test_resolved_state_rejects_reassignment() -> None:
    item = create_queue_item(item_id="queue-8")
    item = assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-1")
    item = transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="in_review")
    item = transition_item(item, actor_id="analyst-1", actor_role="analyst", to_state="resolved")

    with pytest.raises(
        QueueTransitionError, match="cannot assign item from terminal state: resolved"
    ):
        assign_item(item, actor_id="ops-1", actor_role="ops", assignee_id="analyst-2")
