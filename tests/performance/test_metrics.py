"""Tests for the performance metrics engine."""

from __future__ import annotations

from datetime import date

import pytest

from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
)
from inv_man_intake.performance.metrics import (
    PerformanceMetrics,
    compute_metrics,
    compute_metrics_canonical,
)


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


def test_compute_metrics_rejects_duplicate_benchmark_dates() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.01),
                PerformancePoint(as_of=date(2025, 2, 28), value=0.02),
            ),
        )
    )
    duplicate_benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.005),
            PerformancePoint(as_of=date(2025, 1, 31), value=0.006),
        ),
    )

    with pytest.raises(ValueError) as exc:
        compute_metrics(payload, benchmark_monthly=duplicate_benchmark)

    assert str(exc.value) == "monthly[1].as_of duplicates a previous date"


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


def test_compute_metrics_canonical_schema_includes_all_prioritized_metrics() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.01),
                PerformancePoint(as_of=date(2025, 2, 28), value=-0.02),
                PerformancePoint(as_of=date(2025, 3, 31), value=0.03),
            ),
        )
    )

    metrics = compute_metrics(payload)
    schema = metrics.to_canonical_dict()

    assert tuple(schema.keys()) == (
        "annualized_volatility",
        "max_drawdown",
        "sharpe_ratio",
        "sortino_ratio",
        "information_ratio",
        "benchmark_correlation",
        "observation_count",
        "benchmark_observation_count",
        "insufficient_data",
    )
    assert schema["annualized_volatility"] == pytest.approx(0.08717797887081347)
    assert schema["max_drawdown"] == pytest.approx(0.020000000000000018)
    assert schema["sharpe_ratio"] == pytest.approx(0.9176629354822469)
    assert schema["sortino_ratio"] == pytest.approx(1.9999999999999993)
    assert schema["information_ratio"] is None
    assert schema["benchmark_correlation"] is None
    assert schema["observation_count"] == 3
    assert schema["benchmark_observation_count"] == 0
    assert schema["insufficient_data"] == ()


def test_compute_metrics_canonical_returns_stable_schema_directly() -> None:
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

    first = compute_metrics_canonical(payload, benchmark_monthly=benchmark)
    second = compute_metrics_canonical(payload, benchmark_monthly=benchmark)

    assert tuple(first.keys()) == (
        "annualized_volatility",
        "max_drawdown",
        "sharpe_ratio",
        "sortino_ratio",
        "information_ratio",
        "benchmark_correlation",
        "observation_count",
        "benchmark_observation_count",
        "insufficient_data",
    )
    assert first["annualized_volatility"] == pytest.approx(0.052915026221291815)
    assert first["max_drawdown"] == pytest.approx(0.010000000000000009)
    assert first["sharpe_ratio"] == pytest.approx(1.5118578920369083)
    assert first["sortino_ratio"] == pytest.approx(3.9999999999999987)
    assert first["information_ratio"] == pytest.approx(1.9999999999999998)
    assert first["benchmark_correlation"] == pytest.approx(0.9285714285714285)
    assert first["observation_count"] == 3
    assert first["benchmark_observation_count"] == 3
    assert first["insufficient_data"] == ()
    assert first == second


def test_compute_metrics_canonical_matches_dataclass_canonical_output() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.02),
                PerformancePoint(as_of=date(2025, 2, 28), value=-0.01),
                PerformancePoint(as_of=date(2025, 3, 31), value=0.01),
            ),
        )
    )
    benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.01),
            PerformancePoint(as_of=date(2025, 2, 28), value=-0.005),
            PerformancePoint(as_of=date(2025, 3, 31), value=0.008),
        ),
    )

    metrics = compute_metrics(payload, benchmark_monthly=benchmark)
    canonical_direct = compute_metrics_canonical(payload, benchmark_monthly=benchmark)

    assert canonical_direct == metrics.to_canonical_dict()


def test_compute_metrics_canonical_returns_fresh_schema_each_call() -> None:
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

    first = compute_metrics_canonical(payload)
    first["annualized_volatility"] = 999.0
    second = compute_metrics_canonical(payload)

    assert second["annualized_volatility"] == pytest.approx(0.052915026221291815)


def test_compute_metrics_handles_zero_excess_volatility_without_exceptions() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.01),
                PerformancePoint(as_of=date(2025, 2, 28), value=0.01),
            ),
        )
    )

    metrics = compute_metrics(payload)

    assert metrics.annualized_volatility == pytest.approx(0.0)
    assert metrics.sharpe_ratio is None
    assert metrics.sortino_ratio is None
    assert metrics.insufficient_data == ("sharpe_ratio", "sortino_ratio")


def test_compute_metrics_handles_zero_tracking_error_without_exceptions() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            "monthly",
            (
                PerformancePoint(as_of=date(2025, 1, 31), value=0.02),
                PerformancePoint(as_of=date(2025, 2, 28), value=0.01),
                PerformancePoint(as_of=date(2025, 3, 31), value=0.03),
            ),
        )
    )
    benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.01),
            PerformancePoint(as_of=date(2025, 2, 28), value=0.00),
            PerformancePoint(as_of=date(2025, 3, 31), value=0.02),
        ),
    )

    metrics = compute_metrics(payload, benchmark_monthly=benchmark)

    assert metrics.information_ratio is None
    assert metrics.benchmark_correlation == pytest.approx(1.0)
    assert metrics.insufficient_data == ("sortino_ratio", "information_ratio")


def test_compute_metrics_handles_zero_benchmark_variance_without_exceptions() -> None:
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
    flat_benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.005),
            PerformancePoint(as_of=date(2025, 2, 28), value=0.005),
            PerformancePoint(as_of=date(2025, 3, 31), value=0.005),
        ),
    )

    metrics = compute_metrics(payload, benchmark_monthly=flat_benchmark)

    assert metrics.information_ratio == pytest.approx(0.37796447300922725)
    assert metrics.benchmark_correlation is None
    assert metrics.insufficient_data == ("benchmark_correlation",)


def test_to_canonical_dict_rejects_invalid_insufficient_data_order() -> None:
    metrics = PerformanceMetrics(
        annualized_volatility=0.1,
        max_drawdown=0.2,
        sharpe_ratio=0.3,
        sortino_ratio=0.4,
        information_ratio=None,
        benchmark_correlation=None,
        observation_count=3,
        benchmark_observation_count=3,
        insufficient_data=("benchmark_correlation", "information_ratio"),
    )

    with pytest.raises(RuntimeError) as exc:
        metrics.to_canonical_dict()

    assert "insufficient_data must follow prioritized metric order" in str(exc.value)


def test_to_canonical_dict_rejects_negative_counts() -> None:
    metrics = PerformanceMetrics(
        annualized_volatility=0.1,
        max_drawdown=0.2,
        sharpe_ratio=0.3,
        sortino_ratio=0.4,
        information_ratio=0.5,
        benchmark_correlation=0.6,
        observation_count=-1,
        benchmark_observation_count=1,
        insufficient_data=(),
    )

    with pytest.raises(RuntimeError) as exc:
        metrics.to_canonical_dict()

    assert "observation_count cannot be negative" in str(exc.value)
