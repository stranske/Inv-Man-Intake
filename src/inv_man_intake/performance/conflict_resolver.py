"""Resolve multi-source performance conflicts with deterministic precedence rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from inv_man_intake.performance.contracts import (
    PerformancePoint,
    PerformanceSeries,
    validate_series,
)

_DEFAULT_ESCALATION_THRESHOLD_PERCENT = 5.0
_FLOAT_TOLERANCE = 1e-12


@dataclass(frozen=True)
class ConflictAuditEntry:
    """Audit detail for one overlapping point comparison."""

    as_of: date
    xlsx_value: float
    other_value: float
    absolute_difference: float
    percent_difference: float
    is_conflict: bool


@dataclass(frozen=True)
class ConflictResolutionResult:
    """Resolved output plus conflict statistics and escalation signal."""

    resolved_series: PerformanceSeries
    conflict_percentage: float
    escalate: bool
    overlap_count: int
    conflict_count: int
    audit_entries: tuple[ConflictAuditEntry, ...]


def resolve_source_conflicts(
    *,
    xlsx_series: PerformanceSeries | None,
    other_series: PerformanceSeries | None,
    escalation_threshold_percent: float = _DEFAULT_ESCALATION_THRESHOLD_PERCENT,
) -> ConflictResolutionResult:
    """Resolve source conflicts using XLSX precedence and >threshold escalation."""

    if xlsx_series is None and other_series is None:
        raise ValueError("At least one source series is required")

    if xlsx_series is not None:
        validate_series(xlsx_series)
    if other_series is not None:
        validate_series(other_series)

    resolved_series = _resolve_with_precedence(xlsx_series=xlsx_series, other_series=other_series)
    audit_entries = _build_audit_entries(xlsx_series=xlsx_series, other_series=other_series)
    overlap_count = len(audit_entries)
    conflict_count = sum(1 for entry in audit_entries if entry.is_conflict)
    conflict_percentage = (
        0.0 if overlap_count == 0 else (conflict_count / overlap_count) * 100.0
    )

    return ConflictResolutionResult(
        resolved_series=resolved_series,
        conflict_percentage=conflict_percentage,
        escalate=conflict_percentage > escalation_threshold_percent,
        overlap_count=overlap_count,
        conflict_count=conflict_count,
        audit_entries=audit_entries,
    )


def _resolve_with_precedence(
    *, xlsx_series: PerformanceSeries | None, other_series: PerformanceSeries | None
) -> PerformanceSeries:
    if xlsx_series is None and other_series is not None:
        return other_series
    if xlsx_series is not None and other_series is None:
        return xlsx_series

    assert xlsx_series is not None
    assert other_series is not None
    if xlsx_series.frequency != other_series.frequency:
        raise ValueError("Source series frequency mismatch")

    xlsx_map = {point.as_of: point.value for point in xlsx_series.points}
    other_map = {point.as_of: point.value for point in other_series.points}
    all_dates = sorted(set(xlsx_map) | set(other_map))

    resolved_points = [
        PerformancePoint(
            as_of=as_of,
            value=xlsx_map[as_of] if as_of in xlsx_map else other_map[as_of],
        )
        for as_of in all_dates
    ]
    return PerformanceSeries(frequency=xlsx_series.frequency, points=tuple(resolved_points))


def _build_audit_entries(
    *, xlsx_series: PerformanceSeries | None, other_series: PerformanceSeries | None
) -> tuple[ConflictAuditEntry, ...]:
    if xlsx_series is None or other_series is None:
        return ()
    if xlsx_series.frequency != other_series.frequency:
        raise ValueError("Source series frequency mismatch")

    xlsx_map = {point.as_of: point.value for point in xlsx_series.points}
    other_map = {point.as_of: point.value for point in other_series.points}
    overlap_dates = sorted(set(xlsx_map) & set(other_map))

    entries: list[ConflictAuditEntry] = []
    for as_of in overlap_dates:
        xlsx_value = xlsx_map[as_of]
        other_value = other_map[as_of]
        absolute_difference = abs(xlsx_value - other_value)
        percent_difference = _relative_difference_percent(xlsx_value, other_value)
        entries.append(
            ConflictAuditEntry(
                as_of=as_of,
                xlsx_value=xlsx_value,
                other_value=other_value,
                absolute_difference=absolute_difference,
                percent_difference=percent_difference,
                is_conflict=absolute_difference > _FLOAT_TOLERANCE,
            )
        )
    return tuple(entries)


def _relative_difference_percent(value_a: float, value_b: float) -> float:
    denominator = max(abs(value_a), abs(value_b), _FLOAT_TOLERANCE)
    return (abs(value_a - value_b) / denominator) * 100.0
