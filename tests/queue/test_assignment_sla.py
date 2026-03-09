"""Tests for analyst-first queue assignment and SLA fields."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from inv_man_intake.queue.assignment import (
    QueueAssignmentError,
    create_analyst_first_assignment,
    reassign_to_ops_for_block,
    update_sla_breach,
)


def test_analyst_first_assignment_sets_owner_and_sla_fields() -> None:
    created = datetime(2026, 3, 8, 9, 0, 0, tzinfo=UTC)

    record = create_analyst_first_assignment(
        item_id="queue-41-1",
        analyst_id="analyst-1",
        created_at=created,
    )

    assert record.owner_id == "analyst-1"
    assert record.owner_role == "analyst"
    assert record.sla.created_at == created
    assert record.sla.assigned_at == created
    assert record.sla.due_at == datetime(2026, 3, 8, 23, 59, 59, tzinfo=UTC)
    assert record.sla.breached_at is None
    assert record.events[-1].action == "assigned_analyst"


def test_reassign_to_ops_preserves_history_and_updates_sla_assignment_window() -> None:
    created = datetime(2026, 3, 8, 10, 30, 0, tzinfo=UTC)
    reassigned = datetime(2026, 3, 8, 15, 45, 0, tzinfo=UTC)
    record = create_analyst_first_assignment(
        item_id="queue-41-2",
        analyst_id="analyst-2",
        created_at=created,
    )

    updated = reassign_to_ops_for_block(
        record,
        analyst_id="analyst-2",
        ops_id="ops-1",
        reason="blocked by missing custodian feed",
        at=reassigned,
    )

    assert updated.owner_id == "ops-1"
    assert updated.owner_role == "ops"
    assert updated.sla.created_at == created
    assert updated.sla.assigned_at == reassigned
    assert updated.sla.due_at == datetime(2026, 3, 8, 23, 59, 59, tzinfo=UTC)
    assert len(updated.events) == 2
    assert updated.events[-1].action == "reassigned_to_ops"
    assert updated.events[-1].note == "blocked by missing custodian feed"


def test_reassign_rejects_non_owner_analyst() -> None:
    record = create_analyst_first_assignment(
        item_id="queue-41-3",
        analyst_id="analyst-3",
        created_at=datetime(2026, 3, 8, 11, 0, 0, tzinfo=UTC),
    )

    with pytest.raises(
        QueueAssignmentError, match="only current analyst owner can request ops reassignment"
    ):
        reassign_to_ops_for_block(
            record,
            analyst_id="analyst-4",
            ops_id="ops-2",
            reason="requires operations intervention",
        )


def test_same_day_breach_flag_set_after_due_time() -> None:
    created = datetime(2026, 3, 8, 9, 0, 0, tzinfo=UTC)
    record = create_analyst_first_assignment(
        item_id="queue-41-4",
        analyst_id="analyst-5",
        created_at=created,
    )

    breached = update_sla_breach(record, now=datetime(2026, 3, 9, 0, 0, 0, tzinfo=UTC))
    assert breached.sla.breached_at == datetime(2026, 3, 9, 0, 0, 0, tzinfo=UTC)


def test_same_day_breach_flag_not_set_before_due_time() -> None:
    created = datetime(2026, 3, 8, 9, 0, 0, tzinfo=UTC)
    record = create_analyst_first_assignment(
        item_id="queue-41-5",
        analyst_id="analyst-6",
        created_at=created,
    )

    not_breached = update_sla_breach(record, now=datetime(2026, 3, 8, 22, 0, 0, tzinfo=UTC))
    assert not_breached.sla.breached_at is None


def test_sla_requires_timezone_aware_created_at() -> None:
    naive = datetime(2026, 3, 8, 9, 0, 0)

    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        create_analyst_first_assignment(
            item_id="queue-41-6",
            analyst_id="analyst-7",
            created_at=naive,
        )
