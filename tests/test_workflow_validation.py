"""Tests for validation queue ownership and workflow states."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

import pytest

from inv_man_intake.workflow_validation import (
    ValidationWorkflowError,
    claim_for_analyst_triage,
    create_queue_item,
    to_queue_row,
    transfer_owner,
    transition_state,
)


def test_create_item_defaults_to_pending_triage_without_owner() -> None:
    item = create_queue_item(
        item_id="queue-1",
        package_id="pkg-101",
        escalation_reason="confidence_below_threshold",
    )

    assert item.state == "pending_triage"
    assert item.owner_id is None
    assert item.owner_role is None
    assert item.events == ()


def test_claim_requires_pending_item_and_sets_analyst_owner() -> None:
    pending = create_queue_item(
        item_id="queue-2",
        package_id="pkg-102",
        escalation_reason="missing_mandatory_field",
    )

    claimed = claim_for_analyst_triage(pending, analyst_id="analyst-7")

    assert claimed.state == "in_validation"
    assert claimed.owner_id == "analyst-7"
    assert claimed.owner_role == "analyst"
    assert len(claimed.events) == 1
    assert claimed.events[0].action == "claim"


def test_claim_rejects_already_owned_item() -> None:
    pending = create_queue_item(
        item_id="queue-3",
        package_id="pkg-103",
        escalation_reason="parse_conflict",
    )
    claimed = claim_for_analyst_triage(pending, analyst_id="analyst-11")

    with pytest.raises(ValidationWorkflowError, match="already has an owner"):
        claim_for_analyst_triage(claimed, analyst_id="analyst-12")


def test_claim_rejects_non_pending_item_even_when_unowned() -> None:
    pending = create_queue_item(
        item_id="queue-3b",
        package_id="pkg-103b",
        escalation_reason="parse_conflict",
    )
    non_pending_unowned = replace(pending, state="in_validation")

    with pytest.raises(ValidationWorkflowError, match="Only pending_triage items can be claimed"):
        claim_for_analyst_triage(non_pending_unowned, analyst_id="analyst-12")


def test_transition_sequence_and_terminal_block() -> None:
    item = create_queue_item(
        item_id="queue-4",
        package_id="pkg-104",
        escalation_reason="conflicting_returns",
    )
    item = claim_for_analyst_triage(item, analyst_id="analyst-8")
    item = transition_state(
        item,
        actor_id="analyst-8",
        actor_role="analyst",
        to_state="awaiting_manager_response",
    )
    item = transition_state(
        item,
        actor_id="analyst-8",
        actor_role="analyst",
        to_state="in_validation",
    )
    item = transition_state(
        item,
        actor_id="analyst-8",
        actor_role="analyst",
        to_state="completed",
    )

    assert item.state == "completed"

    with pytest.raises(ValidationWorkflowError, match="Invalid transition"):
        transition_state(
            item,
            actor_id="analyst-8",
            actor_role="analyst",
            to_state="in_validation",
        )


def test_invalid_transition_is_rejected() -> None:
    item = create_queue_item(
        item_id="queue-5",
        package_id="pkg-105",
        escalation_reason="low_key_field_coverage",
    )
    item = claim_for_analyst_triage(item, analyst_id="analyst-9")

    with pytest.raises(ValidationWorkflowError, match="Invalid transition"):
        transition_state(
            item,
            actor_id="analyst-9",
            actor_role="analyst",
            to_state="pending_triage",
        )


def test_transfer_to_ops_and_dashboard_projection() -> None:
    item = create_queue_item(
        item_id="queue-6",
        package_id="pkg-106",
        escalation_reason="policy_exception",
    )
    item = claim_for_analyst_triage(item, analyst_id="analyst-10")
    item = transfer_owner(
        item,
        actor_id="analyst-10",
        actor_role="analyst",
        new_owner_id="ops-2",
        new_owner_role="ops",
        note="requires ops decision",
    )
    item = transition_state(
        item,
        actor_id="ops-2",
        actor_role="ops",
        to_state="ops_review",
    )

    row = to_queue_row(item)
    assert row.owner_id == "ops-2"
    assert row.owner_role == "ops"
    assert row.state == "ops_review"
    assert row.next_action == "Ops policy decision"


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        (
            {
                "item_id": "",
                "package_id": "pkg-107",
                "escalation_reason": "missing_mandatory_field",
            },
            "item_id must be non-empty",
        ),
        (
            {
                "item_id": "queue-7",
                "package_id": "",
                "escalation_reason": "missing_mandatory_field",
            },
            "package_id must be non-empty",
        ),
        (
            {
                "item_id": "queue-7",
                "package_id": "pkg-107",
                "escalation_reason": "",
            },
            "escalation_reason must be non-empty",
        ),
    ],
)
def test_create_item_rejects_empty_required_fields(kwargs: dict[str, str], error: str) -> None:
    with pytest.raises(ValidationWorkflowError, match=error):
        create_queue_item(**kwargs)


def test_transfer_owner_rejects_unclaimed_terminal_and_unauthorized_requests() -> None:
    unclaimed = create_queue_item(
        item_id="queue-8",
        package_id="pkg-108",
        escalation_reason="policy_exception",
    )

    with pytest.raises(ValidationWorkflowError, match="must be claimed"):
        transfer_owner(
            unclaimed,
            actor_id="analyst-11",
            actor_role="analyst",
            new_owner_id="ops-3",
            new_owner_role="ops",
        )

    claimed = claim_for_analyst_triage(unclaimed, analyst_id="analyst-11")
    with pytest.raises(ValidationWorkflowError, match="current owner or ops"):
        transfer_owner(
            claimed,
            actor_id="analyst-12",
            actor_role="analyst",
            new_owner_id="ops-3",
            new_owner_role="ops",
        )

    completed = transition_state(
        claimed,
        actor_id="analyst-11",
        actor_role="analyst",
        to_state="completed",
    )
    with pytest.raises(ValidationWorkflowError, match="terminal queue items"):
        transfer_owner(
            completed,
            actor_id="ops-3",
            actor_role="ops",
            new_owner_id="analyst-13",
            new_owner_role="analyst",
        )


def test_transition_state_requires_claim_and_permissions_and_supports_noop() -> None:
    pending = create_queue_item(
        item_id="queue-9",
        package_id="pkg-109",
        escalation_reason="parse_conflict",
    )

    with pytest.raises(ValidationWorkflowError, match="must be claimed"):
        transition_state(
            pending,
            actor_id="analyst-14",
            actor_role="analyst",
            to_state="in_validation",
        )

    claimed = claim_for_analyst_triage(pending, analyst_id="analyst-14")
    no_change = transition_state(
        claimed,
        actor_id="analyst-14",
        actor_role="analyst",
        to_state="in_validation",
    )
    assert no_change == claimed

    with pytest.raises(ValidationWorkflowError, match="current owner or ops"):
        transition_state(
            claimed,
            actor_id="analyst-15",
            actor_role="analyst",
            to_state="ops_review",
        )


@pytest.mark.parametrize(
    ("state", "expected_action"),
    [
        ("pending_triage", "Claim by analyst"),
        ("in_validation", "Review extracted fields"),
        ("awaiting_manager_response", "Collect manager clarification"),
        ("ops_review", "Ops policy decision"),
        ("completed", "No action"),
        ("rejected", "No action"),
    ],
)
def test_to_queue_row_next_action_for_all_states(state: str, expected_action: str) -> None:
    item = create_queue_item(
        item_id=f"queue-row-{state}",
        package_id=f"pkg-row-{state}",
        escalation_reason="policy_exception",
    )
    if state != "pending_triage":
        item = claim_for_analyst_triage(item, analyst_id="analyst-row")
        typed_state = cast(
            Literal[
                "pending_triage",
                "in_validation",
                "awaiting_manager_response",
                "ops_review",
                "completed",
                "rejected",
            ],
            state,
        )
        item = replace(item, state=typed_state)

    row = to_queue_row(item)
    assert row.next_action == expected_action
