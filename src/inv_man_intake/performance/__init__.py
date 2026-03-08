"""Performance ingestion contracts and helpers."""

from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
    validate_payload,
)
from inv_man_intake.performance.ingest import load_document_timeseries, load_xlsx_timeseries
from inv_man_intake.performance.normalize import (
    BenchmarkAlignmentPoint,
    CanonicalMonthPoint,
    NormalizedPerformancePayload,
    build_benchmark_alignment,
    correlation_inputs,
    detect_missing_months,
    normalize_payload,
    normalize_series,
)

__all__ = [
    "BenchmarkAlignmentPoint",
    "CanonicalMonthPoint",
    "NormalizedPerformancePayload",
    "PerformancePayload",
    "PerformancePoint",
    "PerformanceSeries",
    "build_benchmark_alignment",
    "correlation_inputs",
    "detect_missing_months",
    "load_document_timeseries",
    "load_xlsx_timeseries",
    "normalize_payload",
    "normalize_series",
    "validate_payload",
]
