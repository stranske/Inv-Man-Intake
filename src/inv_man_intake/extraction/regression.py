"""Deterministic extraction regression and drift checks."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from inv_man_intake.extraction.providers.base import ExtractionProvider
from inv_man_intake.observability.tracing import TraceEvent


@dataclass(frozen=True)
class GoldenField:
    """Expected normalized value for one extracted field."""

    key: str
    value: str


@dataclass(frozen=True)
class GoldenSample:
    """Offline extraction regression sample."""

    source_doc_id: str
    content: bytes
    expected_fields: tuple[GoldenField, ...]


@dataclass(frozen=True)
class ExtractionRegressionReport:
    """Precision/recall/F1 report for an extraction golden set."""

    provider_name: str
    evaluated_fields: int
    predicted_fields: int
    true_positive_fields: int
    missing_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    unexpected_fields: tuple[str, ...]
    minimum_f1: float

    @property
    def precision(self) -> float:
        if self.predicted_fields == 0:
            return 0.0
        return self.true_positive_fields / self.predicted_fields

    @property
    def recall(self) -> float:
        if self.evaluated_fields == 0:
            return 0.0
        return self.true_positive_fields / self.evaluated_fields

    @property
    def f1(self) -> float:
        precision = self.precision
        recall = self.recall
        if precision == 0.0 and recall == 0.0:
            return 0.0
        return (2 * precision * recall) / (precision + recall)

    @property
    def passes(self) -> bool:
        return self.f1 >= self.minimum_f1


@dataclass(frozen=True)
class DriftScore:
    """Sampled online drift score derived from trace metadata."""

    trace_event_count: int
    matched_trace_count: int
    report: ExtractionRegressionReport

    @property
    def drift_score(self) -> float:
        return 1.0 - self.report.f1


class _ProviderFactory(Protocol):
    def __call__(self) -> ExtractionProvider: ...


def load_golden_samples(path: Path) -> tuple[GoldenSample, ...]:
    """Load a committed extraction golden set from JSON."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    samples: list[GoldenSample] = []
    for item in payload["samples"]:
        expected_payload = item["expected_fields"]
        if isinstance(expected_payload, Mapping):
            expected_fields = tuple(
                GoldenField(key=str(key), value=str(value))
                for key, value in expected_payload.items()
            )
        else:
            expected_fields = tuple(
                GoldenField(key=str(field["key"]), value=str(field["value"]))
                for field in expected_payload
            )
        samples.append(
            GoldenSample(
                source_doc_id=str(item["source_doc_id"]),
                content=str(item["content"]).encode("utf-8"),
                expected_fields=expected_fields,
            )
        )
    return tuple(samples)


def evaluate_extraction_regression(
    *,
    provider_factory: _ProviderFactory,
    samples: tuple[GoldenSample, ...],
    minimum_f1: float,
) -> ExtractionRegressionReport:
    """Run a provider over a golden set and compute field-level precision/recall/F1."""

    if not 0.0 <= minimum_f1 <= 1.0:
        raise ValueError("minimum_f1 must be between 0 and 1")

    provider = provider_factory()
    actual_by_source: dict[str, dict[str, str]] = {}

    for sample in samples:
        result = provider.extract(source_doc_id=sample.source_doc_id, content=sample.content)
        actual_by_source[sample.source_doc_id] = {
            _normalize(field.key): _normalize(field.value) for field in result.fields
        }

    report = _score_fields(
        provider_name=provider.name,
        samples=samples,
        actual_by_source=actual_by_source,
        minimum_f1=minimum_f1,
    )
    return report


def assert_regression_gate(report: ExtractionRegressionReport) -> None:
    """Fail closed when a regression report falls below its configured F1 floor."""

    if report.passes:
        return

    raise AssertionError(
        "extraction regression F1 "
        f"{report.f1:.4f} is below minimum {report.minimum_f1:.4f}; "
        f"missing={list(report.missing_fields)} "
        f"mismatched={list(report.mismatched_fields)} "
        f"unexpected={list(report.unexpected_fields)}"
    )


def score_trace_drift(
    *,
    samples: tuple[GoldenSample, ...],
    trace_events: Iterable[TraceEvent],
    minimum_f1: float,
    provider_name: str = "trace-sample",
) -> DriftScore:
    """Score sampled trace metadata against the same golden-set field contract.

    The helper accepts in-memory trace events or exported LangSmith trace metadata. It
    expects span metadata shaped as ``source_doc_id`` plus a ``fields`` mapping.
    """

    actual_by_source: dict[str, dict[str, str]] = {}
    trace_event_count = 0
    matched_trace_count = 0
    sample_ids = {sample.source_doc_id for sample in samples}

    for event in trace_events:
        trace_event_count += 1
        source_doc_id = event.metadata.get("source_doc_id")
        fields = event.metadata.get("fields")
        if not isinstance(source_doc_id, str) or not isinstance(fields, Mapping):
            continue
        if source_doc_id not in sample_ids:
            continue
        matched_trace_count += 1
        actual_by_source[source_doc_id] = {
            _normalize(str(key)): _normalize(str(value)) for key, value in fields.items()
        }

    report = _score_fields(
        provider_name=provider_name,
        samples=samples,
        actual_by_source=actual_by_source,
        minimum_f1=minimum_f1,
    )
    return DriftScore(
        trace_event_count=trace_event_count,
        matched_trace_count=matched_trace_count,
        report=report,
    )


def _score_fields(
    *,
    provider_name: str,
    samples: tuple[GoldenSample, ...],
    actual_by_source: Mapping[str, Mapping[str, str]],
    minimum_f1: float,
) -> ExtractionRegressionReport:
    expected_total = 0
    predicted_total = 0
    true_positive = 0
    missing: list[str] = []
    mismatched: list[str] = []
    unexpected: list[str] = []

    for sample in samples:
        expected = {
            _normalize(field.key): _normalize(field.value) for field in sample.expected_fields
        }
        actual = actual_by_source.get(sample.source_doc_id, {})
        expected_total += len(expected)
        predicted_total += len(actual)

        for key, expected_value in expected.items():
            field_ref = f"{sample.source_doc_id}:{key}"
            actual_value = actual.get(key)
            if actual_value is None:
                missing.append(field_ref)
            elif actual_value == expected_value:
                true_positive += 1
            else:
                mismatched.append(field_ref)

        for key in sorted(set(actual) - set(expected)):
            unexpected.append(f"{sample.source_doc_id}:{key}")

    return ExtractionRegressionReport(
        provider_name=provider_name,
        evaluated_fields=expected_total,
        predicted_fields=predicted_total,
        true_positive_fields=true_positive,
        missing_fields=tuple(missing),
        mismatched_fields=tuple(mismatched),
        unexpected_fields=tuple(unexpected),
        minimum_f1=minimum_f1,
    )


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())
