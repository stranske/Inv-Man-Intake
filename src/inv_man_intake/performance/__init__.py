"""Performance ingestion contracts and helpers."""

from inv_man_intake.performance.characterize import (
    CharacterizationTag,
    SeriesCharacterization,
    characterize_series,
    gate_scoring_submission,
    require_operator_confirmation,
)
from inv_man_intake.performance.conflict_resolver import (
    ConflictAuditEntry,
    ConflictResolutionResult,
    resolve_source_conflicts,
)
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
    describe_normalization_contract,
    detect_missing_months,
    normalize_payload,
    normalize_series,
)

__all__ = [
    "BenchmarkAlignmentPoint",
    "CanonicalMonthPoint",
    "CanonicalMetricsSchema",
    "CharacterizationTag",
    "ConflictAuditEntry",
    "ConflictResolutionResult",
    "NormalizedPerformancePayload",
    "PerformanceMetrics",
    "PerformancePayload",
    "PerformancePoint",
    "PerformanceSeries",
    "SeriesCharacterization",
    "build_benchmark_alignment",
    "characterize_series",
    "correlation_inputs",
    "compute_metrics",
    "compute_metrics_canonical",
    "describe_normalization_contract",
    "detect_missing_months",
    "gate_scoring_submission",
    "load_document_timeseries",
    "load_xlsx_timeseries",
    "normalize_payload",
    "normalize_series",
    "require_operator_confirmation",
    "resolve_source_conflicts",
    "validate_payload",
]
