"""Tests for ingestion lifecycle service."""

from __future__ import annotations

import pytest

from inv_man_intake.intake.models import IntakeFile
from inv_man_intake.intake.service import IngestionService


def _files() -> list[IntakeFile]:
    return [
        IntakeFile(file_name="manager_deck.pdf", role="investment_deck", source_ref="email:msg-1"),
        IntakeFile(
            file_name="returns.xlsx", role="performance_track_record", source_ref="email:msg-1"
        ),
    ]


def test_happy_path_transitions_received_processing_completed() -> None:
    service = IngestionService()
    received = service.receive_package(
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
    assert received.document_ids == ("pkg_1:doc:0", "pkg_1:doc:1")
    assert completed.document_ids == ("pkg_1:doc:0", "pkg_1:doc:1")
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
    assert escalation.document_ids == ("pkg_2:doc:0", "pkg_2:doc:1")


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


def test_receive_package_rejects_duplicate_package_id() -> None:
    service = IngestionService()
    service.receive_package(
        package_id="pkg_dup",
        firm_id="firm_5",
        fund_id="fund_5",
        files=_files(),
        at="2026-03-01T12:30:00Z",
    )

    with pytest.raises(ValueError, match="already exists"):
        service.receive_package(
            package_id="pkg_dup",
            firm_id="firm_5",
            fund_id="fund_5",
            files=_files(),
            at="2026-03-01T12:31:00Z",
        )


def test_get_events_unknown_package_raises_key_error() -> None:
    service = IngestionService()
    with pytest.raises(KeyError, match="unknown package_id=missing"):
        service.get_events("missing")


def test_document_binding_uses_explicit_document_ids_when_present() -> None:
    service = IngestionService()
    files = [
        IntakeFile(
            file_name="manager_deck.pdf",
            role="investment_deck",
            source_ref="email:msg-1",
            document_id="doc_001",
        ),
        IntakeFile(
            file_name="returns.xlsx",
            role="performance_track_record",
            source_ref="email:msg-1",
            document_id="doc_002",
        ),
    ]
    record = service.receive_package(
        package_id="pkg_docs",
        firm_id="firm_9",
        fund_id="fund_9",
        files=files,
        at="2026-03-01T12:45:00Z",
    )

    assert record.document_ids == ("doc_001", "doc_002")


def test_can_query_record_and_events_by_document_id() -> None:
    service = IngestionService()
    files = [
        IntakeFile(file_name="manager_deck.pdf", role="investment_deck", document_id="doc_A"),
        IntakeFile(file_name="returns.xlsx", role="performance_track_record", document_id="doc_B"),
    ]
    service.receive_package(
        package_id="pkg_lookup",
        firm_id="firm_lookup",
        fund_id="fund_lookup",
        files=files,
        at="2026-03-01T13:00:00Z",
    )
    service.mark_processing(package_id="pkg_lookup", at="2026-03-01T13:01:00Z")

    by_doc = service.get_record_by_document("doc_A")
    by_doc_events = service.get_events_by_document("doc_B")

    assert by_doc.package_id == "pkg_lookup"
    assert [event.to_status for event in by_doc_events] == ["received", "processing"]


def test_duplicate_document_id_rejected_within_package() -> None:
    service = IngestionService()
    files = [
        IntakeFile(file_name="a.pdf", role="investment_deck", document_id="dup_doc"),
        IntakeFile(file_name="b.xlsx", role="performance_track_record", document_id="dup_doc"),
    ]

    with pytest.raises(ValueError, match="duplicate document_id=dup_doc"):
        service.receive_package(
            package_id="pkg_dup_doc",
            firm_id="firm_x",
            fund_id="fund_x",
            files=files,
            at="2026-03-01T13:30:00Z",
        )


def test_duplicate_document_id_rejected_across_packages() -> None:
    service = IngestionService()
    service.receive_package(
        package_id="pkg_alpha",
        firm_id="firm_a",
        fund_id="fund_a",
        files=[IntakeFile(file_name="a.pdf", role="investment_deck", document_id="shared_doc")],
        at="2026-03-01T13:40:00Z",
    )

    with pytest.raises(ValueError, match="document_id=shared_doc already exists"):
        service.receive_package(
            package_id="pkg_beta",
            firm_id="firm_b",
            fund_id="fund_b",
            files=[IntakeFile(file_name="b.pdf", role="investment_deck", document_id="shared_doc")],
            at="2026-03-01T13:41:00Z",
        )


def test_unknown_document_queries_raise_key_error() -> None:
    service = IngestionService()

    with pytest.raises(KeyError, match="unknown document_id=missing_doc"):
        service.get_record_by_document("missing_doc")
    with pytest.raises(KeyError, match="unknown document_id=missing_doc"):
        service.get_events_by_document("missing_doc")
