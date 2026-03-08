"""Tests for validation queue ownership and workflow states."""

from __future__ import annotations

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
