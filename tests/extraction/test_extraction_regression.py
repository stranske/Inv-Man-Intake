"""Golden-set extraction regression gate and drift metric tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider
from inv_man_intake.extraction.regression import (
    GoldenField,
    GoldenSample,
    assert_regression_gate,
    evaluate_extraction_regression,
    load_golden_samples,
    score_trace_drift,
)
from inv_man_intake.observability.tracing import TraceEvent

_GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "extraction_regression_golden.json"


def test_extraction_matches_golden() -> None:
    samples = load_golden_samples(_GOLDEN_PATH)

    report = evaluate_extraction_regression(
        provider_factory=PrimaryRegexExtractionProvider,
        samples=samples,
        minimum_f1=0.95,
    )

    assert report.provider_name == "primary-regex"
    assert report.evaluated_fields == 12
    assert report.predicted_fields == 12
    assert report.true_positive_fields == 12
    assert report.f1 == 1.0
    assert report.passes is True
    assert_regression_gate(report)


def test_extraction_regression_gate_fails_on_perturbed_golden_value() -> None:
    samples = load_golden_samples(_GOLDEN_PATH)
    perturbed = (
        GoldenSample(
            source_doc_id=samples[0].source_doc_id,
            content=samples[0].content,
            expected_fields=(
                GoldenField(key="strategy.name", value="Different Strategy"),
                *samples[0].expected_fields[1:],
            ),
        ),
        *samples[1:],
    )

    report = evaluate_extraction_regression(
        provider_factory=PrimaryRegexExtractionProvider,
        samples=perturbed,
        minimum_f1=0.95,
    )

    assert report.f1 < 0.95
    assert report.mismatched_fields == ("golden-manager-report:strategy.name",)
    with pytest.raises(AssertionError, match="extraction regression F1"):
        assert_regression_gate(report)


def test_trace_drift_scores_sampled_langsmith_metadata() -> None:
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
        _trace_event(source_doc_id="unrelated-doc", fields={"strategy.name": "Ignored"}),
    )

    drift = score_trace_drift(
        samples=samples[:2],
        trace_events=trace_events,
        minimum_f1=0.95,
    )

    assert drift.trace_event_count == 3
    assert drift.matched_trace_count == 2
    assert drift.report.evaluated_fields == 8
    assert drift.report.mismatched_fields == ("golden-credit-review:terms.performance_fee",)
    assert drift.drift_score > 0.0


def _trace_event(*, source_doc_id: str, fields: dict[str, str]) -> TraceEvent:
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
