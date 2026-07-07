"""Golden-set extraction regression gate and drift metric tests."""

from __future__ import annotations

from pathlib import Path
from typing import NoReturn

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


def test_extraction_regression_reports_provider_failures_as_missing_fields() -> None:
    samples = load_golden_samples(_GOLDEN_PATH)

    report = evaluate_extraction_regression(
        provider_factory=_FailingProvider,
        samples=samples[:1],
        minimum_f1=0.95,
    )

    assert report.provider_name == "failing-provider"
    assert report.evaluated_fields == 4
    assert report.predicted_fields == 0
    assert report.true_positive_fields == 0
    assert report.missing_fields == (
        "golden-manager-report:strategy.name",
        "golden-manager-report:benchmark.name",
        "golden-manager-report:terms.management_fee",
        "golden-manager-report:terms.performance_fee",
    )
    assert report.f1 == 0.0


def test_trace_drift_scores_sampled_langsmith_metadata() -> None:
    samples = load_golden_samples(_GOLDEN_PATH)
    date_numeric_sample = GoldenSample(
        source_doc_id="golden-date-fee",
        content=b"not used by trace drift",
        expected_fields=(
            GoldenField(key="terms.management_fee", value="1.50 %"),
            GoldenField(key="document.received_at", value="2026-07-07"),
        ),
    )
    trace_events = (
        _trace_event(
            source_doc_id="golden-manager-report",
            fields={
                "strategy.name": "Global Multi-Asset Income",
                "benchmark.name": "Bloomberg US Aggregate",
                "terms.management_fee": "1.50%",
                "terms.performance_fee": "15%",
            },
            ended=False,
        ),
        _trace_event(
            source_doc_id="golden-manager-report",
            fields={
                "strategy.name": "Global Multi-Asset Income",
                "benchmark.name": "Bloomberg US Aggregate",
                "terms.management_fee": "1.50%",
                "terms.performance_fee": "15%",
            },
            ended=True,
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
        _trace_event(
            source_doc_id="golden-date-fee",
            fields={
                "terms.management_fee": "1.5%",
                "document.received_at": "2026-07-07T13:45:00+00:00",
            },
        ),
        _trace_event(
            source_doc_id="golden-date-fee",
            fields={
                "terms.management_fee": "9.9%",
                "document.received_at": "2026-07-08",
            },
        ),
        _trace_event(source_doc_id="unrelated-doc", fields={"strategy.name": "Ignored"}),
    )

    drift = score_trace_drift(
        samples=(*samples[:2], date_numeric_sample),
        trace_events=trace_events,
        minimum_f1=0.95,
    )

    assert drift.trace_event_count == 6
    assert drift.matched_trace_count == 3
    assert drift.report.evaluated_fields == 10
    assert drift.report.true_positive_fields == 9
    assert drift.report.mismatched_fields == ("golden-credit-review:terms.performance_fee",)
    assert drift.drift_score > 0.0


class _FailingProvider:
    name = "failing-provider"

    def extract(self, *, source_doc_id: str, content: bytes) -> NoReturn:
        raise RuntimeError(f"failed {source_doc_id} with {len(content)} bytes")


def _trace_event(
    *,
    source_doc_id: str,
    fields: dict[str, object],
    ended: bool = True,
) -> TraceEvent:
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
        ended_at="2026-07-07T00:00:01+00:00" if ended else None,
    )
