"""Tests for performance normalization and gap handling."""

from __future__ import annotations

from datetime import date

import pytest

from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
)
from inv_man_intake.performance.normalize import (
    build_benchmark_alignment,
    correlation_inputs,
    normalize_payload,
    normalize_series,
)


def test_normalize_payload_aligns_dates_and_builds_canonical_month_rows() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 4), value=1.1),
                PerformancePoint(as_of=date(2025, 3, 3), value=1.9),
                PerformancePoint(as_of=date(2025, 4, 30), value=-0.2),
            ),
        ),
        quarterly=PerformanceSeries(
            "quarterly",
            (PerformancePoint(as_of=date(2025, 3, 15), value=5.7),),
        ),
        annual=PerformanceSeries(
            "annual",
            (PerformancePoint(as_of=date(2025, 11, 20), value=12.4),),
        ),
    )

    normalized = normalize_payload(payload)

    assert tuple(point.as_of for point in normalized.monthly.points) == (
        date(2025, 1, 31),
        date(2025, 3, 31),
        date(2025, 4, 30),
    )
    assert normalized.quarterly is not None
    assert tuple(point.as_of for point in normalized.quarterly.points) == (date(2025, 3, 31),)
    assert normalized.annual is not None
    assert tuple(point.as_of for point in normalized.annual.points) == (date(2025, 12, 31),)

    assert tuple(point.as_of for point in normalized.canonical_months) == (
        date(2025, 1, 31),
        date(2025, 2, 28),
        date(2025, 3, 31),
        date(2025, 4, 30),
    )
    assert normalized.missing_months == (date(2025, 2, 28),)
    assert normalized.canonical_months[1].missing_month is True
    assert normalized.canonical_months[2].quarterly_value == pytest.approx(5.7)


def test_normalize_payload_is_stable_across_reruns() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 10), value=0.3),
                PerformancePoint(as_of=date(2025, 2, 3), value=0.4),
                PerformancePoint(as_of=date(2025, 3, 2), value=0.5),
            ),
        )
    )

    first = normalize_payload(payload)
    second = normalize_payload(payload)

    assert first == second


def test_normalize_series_rejects_duplicate_period_collapses() -> None:
    monthly = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 1), value=0.1),
            PerformancePoint(as_of=date(2025, 1, 15), value=0.2),
        ),
    )

    with pytest.raises(ValueError) as exc:
        normalize_series(monthly)

    assert str(exc.value) == "monthly[1].as_of normalizes to duplicate period 2025-01-31"


def test_benchmark_alignment_hook_reports_missing_months_and_correlation_inputs() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 6), value=1.0),
                PerformancePoint(as_of=date(2025, 3, 5), value=1.3),
                PerformancePoint(as_of=date(2025, 4, 2), value=1.6),
            ),
        )
    )
    normalized = normalize_payload(payload)

    benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.8),
            PerformancePoint(as_of=date(2025, 2, 28), value=0.9),
            PerformancePoint(as_of=date(2025, 3, 31), value=1.1),
        ),
    )
    alignment = build_benchmark_alignment(normalized, benchmark)

    assert tuple(point.status for point in alignment) == (
        "aligned",
        "missing_portfolio",
        "aligned",
        "missing_benchmark",
    )
    assert correlation_inputs(alignment) == (
        (date(2025, 1, 31), 1.0, 0.8),
        (date(2025, 3, 31), 1.3, 1.1),
    )


def test_benchmark_alignment_requires_monthly_series() -> None:
    normalized = normalize_payload(
        PerformancePayload(
            monthly=PerformanceSeries(
                "monthly",
                (PerformancePoint(as_of=date(2025, 1, 31), value=0.5),),
            )
        )
    )
    quarterly_benchmark = PerformanceSeries(
        "quarterly",
        (PerformancePoint(as_of=date(2025, 3, 31), value=1.2),),
    )

    with pytest.raises(ValueError) as exc:
        build_benchmark_alignment(normalized, quarterly_benchmark)

    assert str(exc.value) == "benchmark alignment requires frequency='monthly'"
