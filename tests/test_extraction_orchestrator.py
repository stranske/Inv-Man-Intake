"""Tests for extraction fallback orchestration."""

from __future__ import annotations

from my_project.extraction_orchestrator import (
    ExtractionFailedError,
    ExtractionOrchestrator,
    RetryPolicy,
)


def test_primary_success_skips_fallback() -> None:
    calls: list[str] = []

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
    )

    result = orchestrator.run({"id": "A-1"})

    assert result.resolved is True
    assert result.provider_used == "primary-provider"
    assert result.retry_count == 0
    assert result.failure_count == 0
    assert result.data == {"id": "A-1", "status": "primary-ok"}
    assert calls == ["primary"]


def test_primary_failure_retries_once_with_fallback() -> None:
    calls: list[str] = []

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
    )

    result = orchestrator.run({"id": "B-2"})

    assert result.resolved is True
    assert result.provider_used == "fallback-provider"
    assert result.retry_count == 1
    assert result.failure_count == 1
    assert result.data == {"id": "B-2", "status": "fallback-ok"}
    assert [attempt.provider for attempt in result.attempts] == [
        "primary-provider",
        "fallback-provider",
    ]
    assert calls == ["primary", "fallback"]


def test_guardrail_blocks_repeated_fallback_attempts() -> None:
    fallback_calls = 0

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
    )

    result = orchestrator.run({"id": "C-3"})

    assert result.resolved is False
    assert result.provider_used is None
    assert result.retry_count == 1
    assert result.failure_count == 2
    assert fallback_calls == 1
    assert result.escalation_reason is not None
