"""Performance ingestion contracts and helpers."""

from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
    validate_payload,
)
from inv_man_intake.performance.ingest import load_document_timeseries, load_xlsx_timeseries
from inv_man_intake.performance.metrics import (
    CanonicalMetricsSchema,
    PerformanceMetrics,
    compute_metrics,
    compute_metrics_canonical,
)
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
    "CanonicalMetricsSchema",
    "NormalizedPerformancePayload",
    "PerformanceMetrics",
    "PerformancePayload",
    "PerformancePoint",
    "PerformanceSeries",
    "build_benchmark_alignment",
    "correlation_inputs",
    "compute_metrics",
    "compute_metrics_canonical",
    "detect_missing_months",
    "load_document_timeseries",
    "load_xlsx_timeseries",
    "normalize_payload",
    "normalize_series",
    "validate_payload",
]
