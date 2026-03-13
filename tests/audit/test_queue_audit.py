"""Tests for queue action audit schema and append-only repository."""

from __future__ import annotations

import pytest

from inv_man_intake.audit import QueueAuditRepository, create_queue_audit_event


def test_create_queue_audit_event_has_required_actor_and_timestamp() -> None:
    event = create_queue_audit_event(
        item_id="queue-1",
        action="claim",
        actor_id="analyst-1",
        actor_role="analyst",
        state_before="pending_triage",
        state_after="in_validation",
        at="2026-03-08T00:00:01+00:00",
    )

    assert event.item_id == "queue-1"
    assert event.actor_id == "analyst-1"
    assert event.at == "2026-03-08T00:00:01+00:00"
    assert event.event_id.startswith("audit_")


def test_repository_append_is_immutable_and_returns_new_instance() -> None:
    base = QueueAuditRepository()
    event = create_queue_audit_event(
        item_id="queue-2",
        action="transfer",
        actor_id="ops-2",
        actor_role="ops",
        at="2026-03-08T00:00:01+00:00",
    )

    updated = base.append(event)

    assert base.all_events() == ()
    assert len(updated.all_events()) == 1


def test_repository_preserves_append_order_for_item_level_trail() -> None:
    repo = QueueAuditRepository()
    repo = repo.append_queue_action(
        item_id="queue-3",
        action="claim",
        actor_id="analyst-3",
        actor_role="analyst",
        state_before="pending_triage",
        state_after="in_validation",
        at="2026-03-08T00:00:01+00:00",
        event_id="e1",
    )
    repo = repo.append_queue_action(
        item_id="queue-3",
        action="override",
        actor_id="ops-7",
        actor_role="ops",
        state_before="in_validation",
        state_after="ops_review",
        override_reason="policy_exception",
        at="2026-03-08T00:00:02+00:00",
        event_id="e2",
    )
    repo = repo.append_queue_action(
        item_id="queue-9",
        action="claim",
        actor_id="analyst-9",
        actor_role="analyst",
        at="2026-03-08T00:00:03+00:00",
        event_id="e3",
    )

    trail = repo.list_for_item("queue-3")
    assert [event.event_id for event in trail] == ["e1", "e2"]
    assert trail[1].override_reason == "policy_exception"


def test_append_rejects_out_of_order_timestamp() -> None:
    repo = QueueAuditRepository().append_queue_action(
        item_id="queue-5",
        action="claim",
        actor_id="analyst-5",
        actor_role="analyst",
        at="2026-03-08T00:00:02+00:00",
    )

    with pytest.raises(ValueError, match="non-decreasing timestamp order"):
        repo.append_queue_action(
            item_id="queue-5",
            action="state_transition",
            actor_id="analyst-5",
            actor_role="analyst",
            at="2026-03-08T00:00:01+00:00",
        )


def test_create_queue_audit_event_metadata_is_immutable() -> None:
    event = create_queue_audit_event(
        item_id="queue-6",
        action="claim",
        actor_id="analyst-6",
        actor_role="analyst",
        metadata={"source": "qa"},
        at="2026-03-08T00:00:01+00:00",
    )

    with pytest.raises(TypeError):
        event.metadata["source"] = "manual"  # type: ignore[index]


def test_repository_append_rejects_equivalent_offset_that_is_chronologically_earlier() -> None:
    repo = QueueAuditRepository().append_queue_action(
        item_id="queue-7",
        action="claim",
        actor_id="analyst-7",
        actor_role="analyst",
        at="2026-03-08T00:30:00+00:00",
    )

    with pytest.raises(ValueError, match="non-decreasing timestamp order"):
        repo.append_queue_action(
            item_id="queue-7",
            action="state_transition",
            actor_id="analyst-7",
            actor_role="analyst",
            at="2026-03-07T19:29:59-05:00",
        )


def test_create_queue_audit_event_normalizes_z_and_offsets_to_utc() -> None:
    from_z = create_queue_audit_event(
        item_id="queue-8",
        action="claim",
        actor_id="analyst-8",
        actor_role="analyst",
        at="2026-03-08T00:00:01Z",
    )
    from_offset = create_queue_audit_event(
        item_id="queue-8",
        action="state_transition",
        actor_id="analyst-8",
        actor_role="analyst",
        at="2026-03-07T19:00:01-05:00",
    )

    assert from_z.at == "2026-03-08T00:00:01+00:00"
    assert from_offset.at == "2026-03-08T00:00:01+00:00"


def test_create_queue_audit_event_rejects_invalid_timestamp() -> None:
    with pytest.raises(ValueError, match="valid ISO-8601 datetime"):
        create_queue_audit_event(
            item_id="queue-9",
            action="claim",
            actor_id="analyst-9",
            actor_role="analyst",
            at="not-a-timestamp",
        )


def test_create_queue_audit_event_validates_required_fields() -> None:
    with pytest.raises(ValueError, match="item_id must be non-empty"):
        create_queue_audit_event(
            item_id="",
            action="claim",
            actor_id="analyst-2",
            actor_role="analyst",
        )
