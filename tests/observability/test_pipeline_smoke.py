"""Observability smoke tests for extraction pipeline tracing and metrics."""

from __future__ import annotations

from inv_man_intake.observability import InMemoryTraceSink, Tracer, new_trace_context
from my_project.extraction_orchestrator import ExtractionFailedError, ExtractionOrchestrator


def _count_metric_event(payload: dict[str, object], counters: dict[str, int]) -> None:
    counters["total"] += 1
    if payload.get("resolved") is True and payload.get("retry_count", 0) == 0:
        counters["primary_success"] += 1
    if payload.get("resolved") is True and payload.get("retry_count", 0) > 0:
        counters["fallback_success"] += 1
    if payload.get("resolved") is False:
        counters["escalated"] += 1


def test_pipeline_smoke_tracing_enabled_keeps_correlation_ids_stable() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=True, sink=sink)
    counters = {
        "total": 0,
        "primary_success": 0,
        "fallback_success": 0,
        "escalated": 0,
    }

    def primary(_: dict[str, object]) -> dict[str, object]:
        raise ExtractionFailedError("primary parse failed")

    def fallback(payload: dict[str, object]) -> dict[str, object]:
        return {"id": payload["id"], "status": "fallback-ok"}

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        metrics_hook=lambda payload: _count_metric_event(payload, counters),
        tracer=tracer,
    )

    trace_context = new_trace_context(tags={"stage": "extract-smoke"})
    result = orchestrator.run({"id": "SMOKE-TRACE-1"}, trace_context=trace_context)

    assert result.resolved is True
    assert result.provider_used == "fallback-provider"
    assert result.retry_count == 1
    assert result.failure_count == 1

    assert len(sink.events) == 6
    assert {event.trace_id for event in sink.events} == {trace_context.trace_id}
    assert {event.run_id for event in sink.events} == {trace_context.run_id}

    assert counters == {
        "total": 1,
        "primary_success": 0,
        "fallback_success": 1,
        "escalated": 0,
    }


def test_pipeline_smoke_tracing_disabled_and_escalation_metrics_path() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=False, sink=sink)
    counters = {
        "total": 0,
        "primary_success": 0,
        "fallback_success": 0,
        "escalated": 0,
    }

    def primary(_: dict[str, object]) -> dict[str, object]:
        raise ExtractionFailedError("primary parse failed")

    def fallback(_: dict[str, object]) -> dict[str, object]:
        raise ExtractionFailedError("fallback parse failed")

    orchestrator = ExtractionOrchestrator(
        primary_name="primary-provider",
        primary_extractor=primary,
        fallback_name="fallback-provider",
        fallback_extractor=fallback,
        metrics_hook=lambda payload: _count_metric_event(payload, counters),
        tracer=tracer,
    )

    result = orchestrator.run({"id": "SMOKE-TRACE-2"})

    assert result.resolved is False
    assert result.escalation_payload is not None
    assert result.retry_count == 1
    assert result.failure_count == 2
    assert sink.events == []
    assert counters == {
        "total": 1,
        "primary_success": 0,
        "fallback_success": 0,
        "escalated": 1,
    }
