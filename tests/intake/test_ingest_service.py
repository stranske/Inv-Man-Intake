"""Tests for ingestion lifecycle service."""

from __future__ import annotations

import pytest

from inv_man_intake.intake.models import IntakeFile
from inv_man_intake.intake.service import IngestionService


def _files() -> list[IntakeFile]:
    return [
        IntakeFile(file_name="manager_deck.pdf", role="investment_deck", source_ref="email:msg-1"),
        IntakeFile(file_name="returns.xlsx", role="performance_track_record", source_ref="email:msg-1"),
    ]


def test_happy_path_transitions_received_processing_completed() -> None:
    service = IngestionService()
    service.receive_package(
        package_id="pkg_1",
        firm_id="firm_1",
        fund_id="fund_1",
        files=_files(),
        at="2026-03-01T09:00:00Z",
    )
    service.mark_processing(package_id="pkg_1", at="2026-03-01T09:01:00Z")
    completed = service.mark_completed(
        package_id="pkg_1",
        at="2026-03-01T09:02:00Z",
        note="ingestion complete",
    )

    assert completed.status == "completed"
    events = service.get_events("pkg_1")
    assert [event.to_status for event in events] == ["received", "processing", "completed"]


def test_escalation_payload_contains_expected_context() -> None:
    service = IngestionService()
    service.receive_package(
        package_id="pkg_2",
        firm_id="firm_2",
        fund_id="fund_2",
        files=_files(),
        at="2026-03-01T10:00:00Z",
    )
    service.mark_processing(package_id="pkg_2", at="2026-03-01T10:01:00Z")

    escalation = service.escalate(
        package_id="pkg_2",
        reason="fallback parser failed",
        at="2026-03-01T10:02:00Z",
        retry_attempted=True,
        fallback_tool="alternate-parser-v1",
    )

    assert escalation.status == "escalated"
    assert escalation.reason == "fallback parser failed"
    assert escalation.retry_attempted is True
    assert escalation.fallback_tool == "alternate-parser-v1"
    assert escalation.file_count == 2


def test_invalid_transition_raises_error() -> None:
    service = IngestionService()
    service.receive_package(
        package_id="pkg_3",
        firm_id="firm_3",
        fund_id="fund_3",
        files=_files(),
        at="2026-03-01T11:00:00Z",
    )
    service.mark_processing(package_id="pkg_3", at="2026-03-01T11:01:00Z")
    service.mark_completed(package_id="pkg_3", at="2026-03-01T11:02:00Z")

    with pytest.raises(ValueError, match="invalid transition"):
        service.mark_processing(package_id="pkg_3", at="2026-03-01T11:03:00Z")


def test_event_order_is_preserved() -> None:
    service = IngestionService()
    service.receive_package(
        package_id="pkg_4",
        firm_id="firm_4",
        fund_id="fund_4",
        files=_files(),
        at="2026-03-01T12:00:00Z",
    )
    service.escalate(
        package_id="pkg_4",
        reason="invalid file bundle",
        at="2026-03-01T12:01:00Z",
        retry_attempted=False,
        fallback_tool=None,
    )

    events = service.get_events("pkg_4")
    assert len(events) == 2
    assert events[0].to_status == "received"
    assert events[1].to_status == "escalated"
