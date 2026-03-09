"""Performance metrics engine for v1 prioritized statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import sqrt
from typing import TypedDict

from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformanceSeries,
    validate_payload,
)

_ANNUALIZATION_FACTOR = 12.0
_ZERO_TOLERANCE = 1e-12
_PRIORITIZED_METRIC_FIELDS = (
    "annualized_volatility",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "information_ratio",
    "benchmark_correlation",
)


class CanonicalMetricsSchema(TypedDict):
    """Stable key-ordered canonical output contract for metric computation."""

    annualized_volatility: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    information_ratio: float | None
    benchmark_correlation: float | None
    observation_count: int
    benchmark_observation_count: int
    insufficient_data: tuple[str, ...]


@dataclass(frozen=True)
class PerformanceMetrics:
    """Canonical performance metrics output schema."""

    annualized_volatility: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    information_ratio: float | None
    benchmark_correlation: float | None
    observation_count: int
    benchmark_observation_count: int
    insufficient_data: tuple[str, ...]

    def to_canonical_dict(self) -> CanonicalMetricsSchema:
        """Return the canonical, stable key-ordered schema for downstream consumers."""

        return {
            "annualized_volatility": self.annualized_volatility,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "information_ratio": self.information_ratio,
            "benchmark_correlation": self.benchmark_correlation,
            "observation_count": self.observation_count,
            "benchmark_observation_count": self.benchmark_observation_count,
            "insufficient_data": self.insufficient_data,
        }


def compute_metrics(
    payload: PerformancePayload,
    *,
    benchmark_monthly: PerformanceSeries | None = None,
    annual_risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    """Compute v1 prioritized performance metrics from canonical monthly returns."""

    validate_payload(payload)
    monthly_returns = [point.value for point in payload.monthly.points]
    risk_free_monthly = annual_risk_free_rate / _ANNUALIZATION_FACTOR

    annualized_volatility = _annualized_volatility(monthly_returns)
    max_drawdown = _max_drawdown(monthly_returns)
    sharpe_ratio = _sharpe_ratio(monthly_returns, risk_free_monthly=risk_free_monthly)
    sortino_ratio = _sortino_ratio(monthly_returns, risk_free_monthly=risk_free_monthly)

    aligned_portfolio: list[float] = []
    aligned_benchmark: list[float] = []
    if benchmark_monthly is not None:
        if benchmark_monthly.frequency != "monthly":
            raise ValueError("benchmark_monthly must use frequency='monthly'")
        aligned_portfolio, aligned_benchmark = _align_monthly_series(
            payload.monthly, benchmark_monthly
        )

    information_ratio = _information_ratio(aligned_portfolio, aligned_benchmark)
    benchmark_correlation = _correlation(aligned_portfolio, aligned_benchmark)

    prioritized_metrics: dict[str, float | None] = {
        "annualized_volatility": annualized_volatility,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "information_ratio": information_ratio,
        "benchmark_correlation": benchmark_correlation,
    }
    insufficient_data = tuple(
        key for key in _PRIORITIZED_METRIC_FIELDS if prioritized_metrics[key] is None
    )

    return PerformanceMetrics(
        annualized_volatility=annualized_volatility,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        information_ratio=information_ratio,
        benchmark_correlation=benchmark_correlation,
        observation_count=len(monthly_returns),
        benchmark_observation_count=len(aligned_portfolio),
        insufficient_data=insufficient_data,
    )


def compute_metrics_canonical(
    payload: PerformancePayload,
    *,
    benchmark_monthly: PerformanceSeries | None = None,
    annual_risk_free_rate: float = 0.0,
) -> CanonicalMetricsSchema:
    """Compute metrics and return the canonical schema directly."""

    return compute_metrics(
        payload,
        benchmark_monthly=benchmark_monthly,
        annual_risk_free_rate=annual_risk_free_rate,
    ).to_canonical_dict()


def _align_monthly_series(
    portfolio_monthly: PerformanceSeries, benchmark_monthly: PerformanceSeries
) -> tuple[list[float], list[float]]:
    benchmark_by_day: dict[date, float] = {
        point.as_of: point.value for point in benchmark_monthly.points
    }
    aligned_portfolio: list[float] = []
    aligned_benchmark: list[float] = []
    for point in portfolio_monthly.points:
        benchmark_value = benchmark_by_day.get(point.as_of)
        if benchmark_value is None:
            continue
        aligned_portfolio.append(point.value)
        aligned_benchmark.append(benchmark_value)
    return aligned_portfolio, aligned_benchmark


def _annualized_volatility(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    return _sample_std_dev(returns) * sqrt(_ANNUALIZATION_FACTOR)


def _max_drawdown(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None

    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for monthly_return in returns:
        equity *= 1.0 + monthly_return
        if equity > peak:
            peak = equity
        drawdown = 1.0 - (equity / peak)
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return max_drawdown


def _sharpe_ratio(returns: list[float], *, risk_free_monthly: float) -> float | None:
    if len(returns) < 2:
        return None

    excess_returns = [value - risk_free_monthly for value in returns]
    volatility = _sample_std_dev(excess_returns)
    if _is_effectively_zero(volatility):
        return None
    return (_mean(excess_returns) / volatility) * sqrt(_ANNUALIZATION_FACTOR)


def _sortino_ratio(returns: list[float], *, risk_free_monthly: float) -> float | None:
    if len(returns) < 2:
        return None

    excess_returns = [value - risk_free_monthly for value in returns]
    downside_squared = [min(0.0, value) ** 2 for value in excess_returns]
    downside_deviation = sqrt(sum(downside_squared) / len(downside_squared))
    if _is_effectively_zero(downside_deviation):
        return None
    return (_mean(excess_returns) / downside_deviation) * sqrt(_ANNUALIZATION_FACTOR)


def _information_ratio(portfolio: list[float], benchmark: list[float]) -> float | None:
    if len(portfolio) < 2 or len(benchmark) < 2:
        return None

    active_returns = [
        portfolio_value - benchmark_value
        for portfolio_value, benchmark_value in zip(portfolio, benchmark, strict=True)
    ]
    tracking_error = _sample_std_dev(active_returns)
    if _is_effectively_zero(tracking_error):
        return None
    return (_mean(active_returns) / tracking_error) * sqrt(_ANNUALIZATION_FACTOR)


def _correlation(portfolio: list[float], benchmark: list[float]) -> float | None:
    if len(portfolio) < 2 or len(benchmark) < 2:
        return None

    std_portfolio = _sample_std_dev(portfolio)
    std_benchmark = _sample_std_dev(benchmark)
    if _is_effectively_zero(std_portfolio) or _is_effectively_zero(std_benchmark):
        return None

    portfolio_mean = _mean(portfolio)
    benchmark_mean = _mean(benchmark)
    covariance = sum(
        (portfolio_value - portfolio_mean) * (benchmark_value - benchmark_mean)
        for portfolio_value, benchmark_value in zip(portfolio, benchmark, strict=True)
    ) / (len(portfolio) - 1)
    return covariance / (std_portfolio * std_benchmark)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _sample_std_dev(values: list[float]) -> float:
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return sqrt(variance)


def _is_effectively_zero(value: float) -> bool:
    return abs(value) <= _ZERO_TOLERANCE
