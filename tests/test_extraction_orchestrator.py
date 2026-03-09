"""Tests for extraction fallback orchestration."""

from __future__ import annotations

from inv_man_intake.observability import InMemoryTraceSink, Tracer
from my_project.extraction_orchestrator import (
    ExtractionFailedError,
    ExtractionOrchestrator,
    RetryPolicy,
)


def test_primary_success_skips_fallback() -> None:
    calls: list[str] = []
    metrics_events: list[dict[str, object]] = []

    def primary(payload: dict[str, object]) -> dict[str, object]:
        calls.append("primary")
        return {"id": payload["id"], "status": "primary-ok"}

    def fallback(_: dict[str, object]) -> dict[str, object]:
        calls.append("fallback")
        return {"status": "fallback-ok"}

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        metrics_hook=metrics_events.append,
    )

    result = orchestrator.run({"id": "A-1"})

    assert result.resolved is True
    assert result.provider_used == "primary-provider"
    assert result.retry_count == 0
    assert result.failure_count == 0
    assert result.escalation_payload is None
    assert result.data == {"id": "A-1", "status": "primary-ok"}
    assert calls == ["primary"]
    assert metrics_events == [
        {
            "resolved": True,
            "provider_used": "primary-provider",
            "retry_count": 0,
            "failure_count": 0,
        }
    ]


def test_primary_failure_retries_once_with_fallback() -> None:
    calls: list[str] = []
    metrics_events: list[dict[str, object]] = []

    def primary(_: dict[str, object]) -> dict[str, object]:
        calls.append("primary")
        raise ExtractionFailedError("parse error")

    def fallback(payload: dict[str, object]) -> dict[str, object]:
        calls.append("fallback")
        return {"id": payload["id"], "status": "fallback-ok"}

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        metrics_hook=metrics_events.append,
    )

    result = orchestrator.run({"id": "B-2"})

    assert result.resolved is True
    assert result.provider_used == "fallback-provider"
    assert result.retry_count == 1
    assert result.failure_count == 1
    assert result.escalation_payload is None
    assert result.data == {"id": "B-2", "status": "fallback-ok"}
    assert [attempt.provider for attempt in result.attempts] == [
        "primary-provider",
        "fallback-provider",
    ]
    assert calls == ["primary", "fallback"]
    assert metrics_events == [
        {
            "resolved": True,
            "provider_used": "fallback-provider",
            "retry_count": 1,
            "failure_count": 1,
        }
    ]


def test_guardrail_blocks_repeated_fallback_attempts() -> None:
    fallback_calls = 0
    metrics_events: list[dict[str, object]] = []

    def primary(_: dict[str, object]) -> dict[str, object]:
        raise ExtractionFailedError("primary failed")

    def fallback(_: dict[str, object]) -> dict[str, object]:
        nonlocal fallback_calls
        fallback_calls += 1
        raise ExtractionFailedError("fallback failed")

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        policy=RetryPolicy(max_total_attempts=3, max_fallback_attempts=1),
        metrics_hook=metrics_events.append,
    )

    result = orchestrator.run({"id": "C-3"})

    assert result.resolved is False
    assert result.provider_used is None
    assert result.retry_count == 1
    assert result.failure_count == 2
    assert result.escalation_route == "ops_review"
    assert fallback_calls == 1
    assert result.escalation_reason is not None
    assert result.escalation_payload == {
        "item_id": "C-3",
        "input_payload": {"id": "C-3"},
        "escalation_route": "ops_review",
        "escalation_reason": "fallback-provider: fallback failed",
        "retry_count": 1,
        "failure_count": 2,
        "failed_providers": ["primary-provider", "fallback-provider"],
        "errors": [
            "primary-provider: primary failed",
            "fallback-provider: fallback failed",
        ],
    }
    assert metrics_events == [
        {
            "resolved": False,
            "provider_used": None,
            "retry_count": 1,
            "failure_count": 2,
        }
    ]


def test_fallback_retries_until_success_within_policy_limits() -> None:
    fallback_calls = 0

    def primary(_: dict[str, object]) -> dict[str, object]:
        raise ExtractionFailedError("primary failed")

    def fallback(payload: dict[str, object]) -> dict[str, object]:
        nonlocal fallback_calls
        fallback_calls += 1
        if fallback_calls == 1:
            raise ExtractionFailedError("fallback transient")
        return {"id": payload["id"], "status": "fallback-ok"}

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        policy=RetryPolicy(max_total_attempts=3, max_fallback_attempts=2),
    )

    result = orchestrator.run({"id": "C-4b"})

    assert result.resolved is True
    assert result.provider_used == "fallback-provider"
    assert result.retry_count == 2
    assert result.failure_count == 2
    assert fallback_calls == 2
    assert [attempt.provider for attempt in result.attempts] == [
        "primary-provider",
        "fallback-provider",
        "fallback-provider",
    ]
    assert [attempt.success for attempt in result.attempts] == [False, False, True]


def test_guardrail_blocks_fallback_when_provider_names_match() -> None:
    fallback_calls = 0

    def provider(_: dict[str, object]) -> dict[str, object]:
        raise ExtractionFailedError("shared provider failed")

    def fallback(_: dict[str, object]) -> dict[str, object]:
        nonlocal fallback_calls
        fallback_calls += 1
        raise AssertionError("fallback should be blocked by provider-name guardrail")

    orchestrator = ExtractionOrchestrator(
        primary_name="shared-provider",
        primary_extractor=provider,
        fallback_name="shared-provider",
        fallback_extractor=fallback,
        policy=RetryPolicy(max_total_attempts=3, max_fallback_attempts=2),
    )

    result = orchestrator.run({"id": "C-4c"})

    assert result.resolved is False
    assert result.retry_count == 0
    assert result.failure_count == 1
    assert result.escalation_route == "pending_triage"
    assert fallback_calls == 0
    assert [attempt.provider for attempt in result.attempts] == ["shared-provider"]


def test_primary_failure_routes_to_pending_triage_when_fallback_is_disabled() -> None:
    def primary(_: dict[str, object]) -> dict[str, object]:
        raise ExtractionFailedError("primary failed")

    def fallback(_: dict[str, object]) -> dict[str, object]:
        raise AssertionError("fallback should not run")

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        policy=RetryPolicy(max_total_attempts=1, max_fallback_attempts=0),
    )

    result = orchestrator.run({"id": "C-4"})

    assert result.resolved is False
    assert result.retry_count == 0
    assert result.failure_count == 1
    assert result.escalation_route == "pending_triage"
    assert result.escalation_payload == {
        "item_id": "C-4",
        "input_payload": {"id": "C-4"},
        "escalation_route": "pending_triage",
        "escalation_reason": "primary-provider: primary failed",
        "retry_count": 0,
        "failure_count": 1,
        "failed_providers": ["primary-provider"],
        "errors": ["primary-provider: primary failed"],
    }


def test_orchestrator_emits_trace_events_for_primary_success() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=True, sink=sink)

    def primary(payload: dict[str, object]) -> dict[str, object]:
        return {"id": payload["id"], "status": "primary-ok"}

    def fallback(_: dict[str, object]) -> dict[str, object]:
        return {"status": "fallback-ok"}

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        tracer=tracer,
    )

    result = orchestrator.run({"id": "TRACE-1"})

    assert result.resolved is True
    assert [event.name for event in sink.events] == [
        "extraction_orchestrator.run",
        "extraction_orchestrator.primary_attempt",
        "extraction_orchestrator.primary_attempt",
        "extraction_orchestrator.run",
    ]
    assert sink.events[1].metadata["provider"] == "primary-provider"


def test_orchestrator_emits_trace_events_for_fallback_attempt() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=True, sink=sink)

    def primary(_: dict[str, object]) -> dict[str, object]:
        raise ExtractionFailedError("primary failed")

    def fallback(payload: dict[str, object]) -> dict[str, object]:
        return {"id": payload["id"], "status": "fallback-ok"}

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        tracer=tracer,
    )

    result = orchestrator.run({"id": "TRACE-2"})

    assert result.resolved is True
    assert [event.name for event in sink.events] == [
        "extraction_orchestrator.run",
        "extraction_orchestrator.primary_attempt",
        "extraction_orchestrator.primary_attempt",
        "extraction_orchestrator.fallback_attempt",
        "extraction_orchestrator.fallback_attempt",
        "extraction_orchestrator.run",
    ]
    assert sink.events[1].metadata["provider"] == "primary-provider"
    assert sink.events[3].metadata["provider"] == "fallback-provider"
