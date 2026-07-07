"""Observability-facing extraction drift reports over traced extraction metadata."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from inv_man_intake.extraction.regression import (
    DriftScore,
    GoldenSample,
    score_trace_drift,
)
from inv_man_intake.observability.tracing import TraceEvent


@dataclass(frozen=True)
class ExtractionDriftRecord:
    """Numeric drift report safe to emit as an observability artifact."""

    provider_name: str
    trace_event_count: int
    matched_trace_count: int
    evaluated_fields: int
    true_positive_fields: int
    f1: float
    drift_score: float
    mismatched_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]

    @property
    def status(self) -> str:
        return "pass" if self.drift_score == 0.0 else "drift"

    def as_metric_fields(self) -> dict[str, int | float | str]:
        """Return stable scalar fields for metrics, logs, and PR evidence comments."""

        return {
            "provider_name": self.provider_name,
            "trace_event_count": self.trace_event_count,
            "matched_trace_count": self.matched_trace_count,
            "evaluated_fields": self.evaluated_fields,
            "true_positive_fields": self.true_positive_fields,
            "f1": self.f1,
            "drift_score": self.drift_score,
            "status": self.status,
        }


def score_extraction_trace_drift(
    *,
    samples: tuple[GoldenSample, ...],
    trace_events: Iterable[TraceEvent],
    minimum_f1: float,
    provider_name: str = "langsmith-trace-sample",
) -> ExtractionDriftRecord:
    """Score sampled LangSmith trace metadata and return a numeric drift record."""

    if not 0.0 <= minimum_f1 <= 1.0:
        raise ValueError("minimum_f1 must be between 0 and 1")

    score = score_trace_drift(
        samples=samples,
        trace_events=trace_events,
        minimum_f1=minimum_f1,
        provider_name=provider_name,
    )
    return _record_from_score(score)


def _record_from_score(score: DriftScore) -> ExtractionDriftRecord:
    return ExtractionDriftRecord(
        provider_name=score.report.provider_name,
        trace_event_count=score.trace_event_count,
        matched_trace_count=score.matched_trace_count,
        evaluated_fields=score.report.evaluated_fields,
        true_positive_fields=score.report.true_positive_fields,
        f1=score.report.f1,
        drift_score=score.drift_score,
        mismatched_fields=score.report.mismatched_fields,
        missing_fields=score.report.missing_fields,
    )
