"""Tests for performance source conflict resolver behavior."""

from __future__ import annotations

from datetime import date

import pytest

from inv_man_intake.performance.conflict_resolver import resolve_source_conflicts
from inv_man_intake.performance.contracts import PerformancePoint, PerformanceSeries


def test_resolver_prefers_xlsx_values_on_overlapping_conflicts() -> None:
    xlsx = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.10),
            PerformancePoint(as_of=date(2025, 2, 28), value=0.05),
        ),
    )
    other = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.11),
            PerformancePoint(as_of=date(2025, 2, 28), value=0.05),
            PerformancePoint(as_of=date(2025, 3, 31), value=-0.01),
        ),
    )

    result = resolve_source_conflicts(xlsx_series=xlsx, other_series=other)

    assert tuple((point.as_of, point.value) for point in result.resolved_series.points) == (
        (date(2025, 1, 31), 0.10),
        (date(2025, 2, 28), 0.05),
        (date(2025, 3, 31), -0.01),
    )
    assert result.overlap_count == 2
    assert result.conflict_count == 1
    assert result.conflict_percentage == pytest.approx(50.0)
    assert result.escalate is True
    assert len(result.audit_entries) == 2
    assert result.audit_entries[0].is_conflict is True
    assert result.audit_entries[1].is_conflict is False


def test_conflict_threshold_boundary_at_five_percent_does_not_escalate() -> None:
    points_xlsx: list[PerformancePoint] = []
    points_other: list[PerformancePoint] = []
    for idx in range(20):
        as_of = _month_end_from_index(idx)
        points_xlsx.append(PerformancePoint(as_of=as_of, value=0.01 * idx))
        points_other.append(PerformancePoint(as_of=as_of, value=0.01 * idx))
    points_other[7] = PerformancePoint(as_of=points_other[7].as_of, value=0.123)

    result = resolve_source_conflicts(
        xlsx_series=PerformanceSeries("monthly", tuple(points_xlsx)),
        other_series=PerformanceSeries("monthly", tuple(points_other)),
    )

    assert result.overlap_count == 20
    assert result.conflict_count == 1
    assert result.conflict_percentage == pytest.approx(5.0)
    assert result.escalate is False


def test_conflict_threshold_above_five_percent_escalates() -> None:
    points_xlsx: list[PerformancePoint] = []
    points_other: list[PerformancePoint] = []
    for idx in range(20):
        as_of = _month_end_from_index(idx)
        points_xlsx.append(PerformancePoint(as_of=as_of, value=0.02 * idx))
        points_other.append(PerformancePoint(as_of=as_of, value=0.02 * idx))
    points_other[2] = PerformancePoint(as_of=points_other[2].as_of, value=0.31)
    points_other[19] = PerformancePoint(as_of=points_other[19].as_of, value=-0.44)

    result = resolve_source_conflicts(
        xlsx_series=PerformanceSeries("monthly", tuple(points_xlsx)),
        other_series=PerformanceSeries("monthly", tuple(points_other)),
    )

    assert result.overlap_count == 20
    assert result.conflict_count == 2
    assert result.conflict_percentage == pytest.approx(10.0)
    assert result.escalate is True


def test_resolver_handles_no_overlap_without_escalation() -> None:
    xlsx = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.1),
            PerformancePoint(as_of=date(2025, 2, 28), value=0.2),
        ),
    )
    other = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 3, 31), value=0.3),
            PerformancePoint(as_of=date(2025, 4, 30), value=0.4),
        ),
    )

    result = resolve_source_conflicts(xlsx_series=xlsx, other_series=other)

    assert result.overlap_count == 0
    assert result.conflict_count == 0
    assert result.conflict_percentage == pytest.approx(0.0)
    assert result.escalate is False
    assert result.audit_entries == ()


def test_resolver_validates_frequency_mismatch() -> None:
    xlsx = PerformanceSeries(
        "monthly",
        (PerformancePoint(as_of=date(2025, 1, 31), value=0.1),),
    )
    other = PerformanceSeries(
        "quarterly",
        (PerformancePoint(as_of=date(2025, 3, 31), value=0.2),),
    )

    with pytest.raises(ValueError) as exc:
        resolve_source_conflicts(xlsx_series=xlsx, other_series=other)

    assert str(exc.value) == "Source series frequency mismatch"


def test_resolver_accepts_single_source_inputs() -> None:
    xlsx = PerformanceSeries(
        "monthly",
        (PerformancePoint(as_of=date(2025, 1, 31), value=0.1),),
    )

    xlsx_only = resolve_source_conflicts(xlsx_series=xlsx, other_series=None)
    assert xlsx_only.resolved_series == xlsx
    assert xlsx_only.conflict_percentage == pytest.approx(0.0)
    assert xlsx_only.escalate is False

    other = PerformanceSeries(
        "monthly",
        (PerformancePoint(as_of=date(2025, 2, 28), value=0.2),),
    )
    other_only = resolve_source_conflicts(xlsx_series=None, other_series=other)
    assert other_only.resolved_series == other
    assert other_only.conflict_percentage == pytest.approx(0.0)
    assert other_only.escalate is False


def _month_end_from_index(index: int) -> date:
    year = 2025 + ((index) // 12)
    month = (index % 12) + 1
    if month == 2:
        return date(year, month, 28)
    if month in {4, 6, 9, 11}:
        return date(year, month, 30)
    return date(year, month, 31)
