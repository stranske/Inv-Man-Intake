"""Tests for observability-owned extraction drift records."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.extraction.regression import load_golden_samples
from inv_man_intake.observability.extraction_drift import score_extraction_trace_drift
from inv_man_intake.observability.tracing import TraceEvent

_GOLDEN_PATH = (
    Path(__file__).resolve().parents[1]
    / "extraction"
    / "golden"
    / "extraction_regression_golden.json"
)


def test_score_extraction_trace_drift_returns_numeric_observability_record() -> None:
    samples = load_golden_samples(_GOLDEN_PATH)
    trace_events = (
        _trace_event(
            source_doc_id="golden-manager-report",
            fields={
                "strategy.name": "Global Multi-Asset Income",
                "benchmark.name": "Bloomberg US Aggregate",
                "terms.management_fee": "1.50%",
                "terms.performance_fee": "15%",
            },
        ),
        _trace_event(
            source_doc_id="golden-credit-review",
            fields={
                "strategy.name": "Defensive Credit Alpha",
                "benchmark.name": "ICE BofA US Corp",
                "terms.management_fee": "0.95%",
                "terms.performance_fee": "99%",
            },
        ),
    )

    record = score_extraction_trace_drift(
        samples=samples[:2],
        trace_events=trace_events,
        minimum_f1=0.95,
    )

    assert record.provider_name == "langsmith-trace-sample"
    assert record.trace_event_count == 2
    assert record.matched_trace_count == 2
    assert record.evaluated_fields == 8
    assert record.true_positive_fields == 7
    assert record.mismatched_fields == ("golden-credit-review:terms.performance_fee",)
    assert record.drift_score == 0.125
    assert record.status == "drift"
    assert record.as_metric_fields()["drift_score"] == 0.125


def _trace_event(*, source_doc_id: str, fields: dict[str, object]) -> TraceEvent:
    return TraceEvent(
        kind="span",
        span_id=f"span-{source_doc_id}",
        trace_id="trace-golden",
        run_id=None,
        name="extract.fields",
        parent_run_id=None,
        parent_span_id=None,
        metadata={"source_doc_id": source_doc_id, "fields": fields},
        started_at="2026-07-07T00:00:00+00:00",
        ended_at="2026-07-07T00:00:01+00:00",
    )
