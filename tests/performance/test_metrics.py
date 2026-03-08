"""Tests for the performance metrics engine."""

from __future__ import annotations

from datetime import date

import pytest

from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
)
from inv_man_intake.performance.metrics import compute_metrics


def test_compute_metrics_returns_expected_values_for_known_fixture() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.02),
                PerformancePoint(as_of=date(2025, 2, 28), value=-0.01),
                PerformancePoint(as_of=date(2025, 3, 31), value=0.03),
                PerformancePoint(as_of=date(2025, 4, 30), value=0.00),
                PerformancePoint(as_of=date(2025, 5, 31), value=-0.02),
                PerformancePoint(as_of=date(2025, 6, 30), value=0.01),
            ),
        )
    )
    benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.01),
            PerformancePoint(as_of=date(2025, 2, 28), value=-0.015),
            PerformancePoint(as_of=date(2025, 3, 31), value=0.02),
            PerformancePoint(as_of=date(2025, 4, 30), value=0.005),
            PerformancePoint(as_of=date(2025, 5, 31), value=-0.01),
            PerformancePoint(as_of=date(2025, 6, 30), value=0.008),
        ),
    )

    metrics = compute_metrics(payload, benchmark_monthly=benchmark)

    assert metrics.annualized_volatility == pytest.approx(0.06480740698407861)
    assert metrics.max_drawdown == pytest.approx(0.020000000000000018)
    assert metrics.sharpe_ratio == pytest.approx(0.9258200997725514)
    assert metrics.sortino_ratio == pytest.approx(1.8973665961010278)
    assert metrics.information_ratio == pytest.approx(0.8528028654224415)
    assert metrics.benchmark_correlation == pytest.approx(0.9292586263707134)
    assert metrics.observation_count == 6
    assert metrics.benchmark_observation_count == 6
    assert metrics.insufficient_data == ()


def test_compute_metrics_handles_insufficient_windows_gracefully() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (PerformancePoint(as_of=date(2025, 1, 31), value=0.01),),
        )
    )
    benchmark = PerformanceSeries(
        "monthly",
        (PerformancePoint(as_of=date(2025, 1, 31), value=0.008),),
    )

    metrics = compute_metrics(payload, benchmark_monthly=benchmark)

    assert metrics.annualized_volatility is None
    assert metrics.max_drawdown is None
    assert metrics.sharpe_ratio is None
    assert metrics.sortino_ratio is None
    assert metrics.information_ratio is None
    assert metrics.benchmark_correlation is None
    assert metrics.insufficient_data == (
        "annualized_volatility",
        "max_drawdown",
        "sharpe_ratio",
        "sortino_ratio",
        "information_ratio",
        "benchmark_correlation",
    )


def test_compute_metrics_requires_monthly_benchmark_frequency() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.01),
                PerformancePoint(as_of=date(2025, 2, 28), value=0.02),
            ),
        )
    )
    quarterly_benchmark = PerformanceSeries(
        "quarterly",
        (PerformancePoint(as_of=date(2025, 3, 31), value=0.03),),
    )

    with pytest.raises(ValueError) as exc:
        compute_metrics(payload, benchmark_monthly=quarterly_benchmark)

    assert str(exc.value) == "benchmark_monthly must use frequency='monthly'"


def test_compute_metrics_flags_benchmark_metrics_when_overlap_is_too_small() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.03),
                PerformancePoint(as_of=date(2025, 2, 28), value=-0.01),
            ),
        )
    )
    benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 2, 28), value=-0.02),
            PerformancePoint(as_of=date(2025, 3, 31), value=0.01),
        ),
    )

    metrics = compute_metrics(payload, benchmark_monthly=benchmark)

    assert metrics.observation_count == 2
    assert metrics.benchmark_observation_count == 1
    assert metrics.information_ratio is None
    assert metrics.benchmark_correlation is None
    assert metrics.insufficient_data == ("information_ratio", "benchmark_correlation")


def test_compute_metrics_is_reproducible_for_identical_inputs() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.01),
                PerformancePoint(as_of=date(2025, 2, 28), value=0.02),
                PerformancePoint(as_of=date(2025, 3, 31), value=-0.01),
            ),
        )
    )
    benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.00),
            PerformancePoint(as_of=date(2025, 2, 28), value=0.01),
            PerformancePoint(as_of=date(2025, 3, 31), value=-0.005),
        ),
    )

    first = compute_metrics(payload, benchmark_monthly=benchmark)
    second = compute_metrics(payload, benchmark_monthly=benchmark)

    assert first == second
