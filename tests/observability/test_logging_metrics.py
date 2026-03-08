"""Tests for correlation logging context and operational metric emission."""

from __future__ import annotations

from inv_man_intake.observability.logging import (
    LogContext,
    build_log_record,
    ensure_correlation_id,
    extract_correlation_id,
    inject_correlation_id,
)
from inv_man_intake.observability.metrics import (
    ESCALATION_COUNT,
    FAILURE_COUNT,
    FALLBACK_COUNT,
    LATENCY_MS,
    InMemoryMetrics,
)


def test_correlation_id_round_trip_and_propagation() -> None:
    correlation_id = ensure_correlation_id()
    outbound = inject_correlation_id(correlation_id)
    extracted = extract_correlation_id(outbound)

    assert extracted == correlation_id
    assert ensure_correlation_id(outbound) == correlation_id


def test_build_log_record_contains_required_operational_fields() -> None:
    context = LogContext(
        correlation_id="corr_abc123",
        stage="extraction",
        status="failed",
        error_code="timeout",
    )
    record = build_log_record(
        context=context,
        message="provider timeout",
        level="ERROR",
        fields={"retry_count": 2},
    )

    assert record["correlation_id"] == "corr_abc123"
    assert record["stage"] == "extraction"
    assert record["status"] == "failed"
    assert record["error_code"] == "timeout"
    assert record["level"] == "ERROR"
    assert record["retry_count"] == 2
    assert "timestamp" in record


def test_inmemory_metrics_records_core_counters_and_latency() -> None:
    metrics = InMemoryMetrics()

    metrics.record_failure(stage="intake", error_code="parse_error")
    metrics.record_fallback(stage="extraction", reason="low_confidence")
    metrics.record_escalation(stage="scoring", reason="manual_override")
    metrics.record_latency(stage="intake", milliseconds=125.5, status="success")

    assert metrics.count(
        FAILURE_COUNT,
        tags={"stage": "intake", "error_code": "parse_error"},
    ) == 1.0
    assert metrics.count(
        FALLBACK_COUNT,
        tags={"stage": "extraction", "reason": "low_confidence"},
    ) == 1.0
    assert metrics.count(
        ESCALATION_COUNT,
        tags={"stage": "scoring", "reason": "manual_override"},
    ) == 1.0
    assert metrics.count(
        LATENCY_MS,
        tags={"stage": "intake", "status": "success"},
    ) == 125.5


def test_metrics_count_uses_name_and_exact_tags() -> None:
    metrics = InMemoryMetrics()

    metrics.record_failure(stage="intake", error_code="parse_error")
    metrics.record_failure(stage="extraction", error_code="provider_error")

    assert metrics.count(
        FAILURE_COUNT,
        tags={"stage": "intake", "error_code": "parse_error"},
    ) == 1.0
    assert metrics.count(
        FAILURE_COUNT,
        tags={"stage": "ingest", "error_code": "parse_error"},
    ) == 0.0
