"""Performance normalization helpers for canonical month-aligned outputs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
    validate_payload,
    validate_series,
)

BenchmarkAlignmentStatus = Literal["aligned", "missing_portfolio", "missing_benchmark"]
DateInput = date | datetime | str

NORMALIZATION_ASSUMPTIONS: tuple[str, ...] = (
    "Monthly series is required and drives canonical month range boundaries.",
    "All canonical output dates use ISO 8601 calendar dates (YYYY-MM-DD).",
    "Date normalization snaps input points to period-end boundaries by frequency.",
    "Input series for a frequency must be strictly increasing and deterministic.",
)
NORMALIZATION_LIMITATIONS: tuple[str, ...] = (
    "No source conflict arbitration across competing provider payloads.",
    "No interpolation or advanced imputation for missing months.",
    "No correlation or other statistics are computed in normalization stage.",
    "No support for frequencies outside monthly, quarterly, and annual.",
)


@dataclass(frozen=True)
class CanonicalMonthPoint:
    """One canonical month row after frequency/date normalization."""

    as_of: date
    monthly_value: float | None
    quarterly_value: float | None
    annual_value: float | None
    missing_month: bool


@dataclass(frozen=True)
class NormalizedPerformancePayload:
    """Normalized payload with month-level canonical rows and gap flags."""

    monthly: PerformanceSeries
    quarterly: PerformanceSeries | None
    annual: PerformanceSeries | None
    canonical_months: tuple[CanonicalMonthPoint, ...]
    missing_months: tuple[date, ...]


@dataclass(frozen=True)
class BenchmarkAlignmentPoint:
    """Aligned portfolio/benchmark value pair for one month."""

    as_of: date
    portfolio_value: float | None
    benchmark_value: float | None
    status: BenchmarkAlignmentStatus


def describe_normalization_contract() -> dict[str, tuple[str, ...]]:
    """Return deterministic assumptions and known v1 limitations for normalization."""

    return {
        "assumptions": NORMALIZATION_ASSUMPTIONS,
        "limitations": NORMALIZATION_LIMITATIONS,
    }


def normalize_payload(payload: PerformancePayload) -> NormalizedPerformancePayload:
    """Normalize frequencies to period-end dates and build canonical monthly rows."""

    validate_payload(payload)

    monthly = normalize_series(payload.monthly)
    quarterly = normalize_series(payload.quarterly) if payload.quarterly is not None else None
    annual = normalize_series(payload.annual) if payload.annual is not None else None

    missing_months = detect_missing_months(monthly)
    canonical_months = _build_canonical_months(monthly, quarterly, annual)

    return NormalizedPerformancePayload(
        monthly=monthly,
        quarterly=quarterly,
        annual=annual,
        canonical_months=canonical_months,
        missing_months=missing_months,
    )


def normalize_date_input(raw_date: DateInput, *, frequency: str | None = None) -> date:
    """Parse heterogeneous date values and optionally align to a frequency period end."""

    parsed = _parse_date_value(raw_date)
    if frequency is None:
        return parsed
    return _normalizer_for_frequency(frequency)(parsed)


def canonical_date_string(raw_date: DateInput, *, frequency: str | None = None) -> str:
    """Return canonical YYYY-MM-DD representation for a date-like input."""

    return normalize_date_input(raw_date, frequency=frequency).isoformat()


def normalize_series(series: PerformanceSeries) -> PerformanceSeries:
    """Normalize dates to period-end boundaries for the series frequency."""

    validate_series(series)
    normalizer = _normalizer_for_frequency(series.frequency)

    normalized_points: list[PerformancePoint] = []
    seen_dates: set[date] = set()
    prev_day: date | None = None

    for idx, point in enumerate(series.points):
        normalized_day = normalizer(point.as_of)
        if normalized_day in seen_dates:
            raise ValueError(
                f"{series.frequency}[{idx}].as_of normalizes to duplicate period "
                f"{normalized_day.isoformat()}"
            )
        if prev_day is not None and normalized_day <= prev_day:
            raise ValueError(
                f"{series.frequency}[{idx}].as_of normalizes out of order at "
                f"{normalized_day.isoformat()}"
            )

        seen_dates.add(normalized_day)
        prev_day = normalized_day
        normalized_points.append(PerformancePoint(as_of=normalized_day, value=point.value))

    normalized = PerformanceSeries(frequency=series.frequency, points=tuple(normalized_points))
    validate_series(normalized)
    return normalized


def detect_missing_months(monthly_series: PerformanceSeries) -> tuple[date, ...]:
    """Detect missing months in the monthly series range (inclusive)."""

    if monthly_series.frequency != "monthly":
        raise ValueError("detect_missing_months requires frequency='monthly'")
    normalized_monthly = normalize_series(monthly_series)
    if not normalized_monthly.points:
        return ()

    actual = {point.as_of for point in normalized_monthly.points}
    start = normalized_monthly.points[0].as_of
    end = normalized_monthly.points[-1].as_of

    missing: list[date] = []
    for month_end in _iter_month_ends(start, end):
        if month_end not in actual:
            missing.append(month_end)
    return tuple(missing)


def build_benchmark_alignment(
    normalized: NormalizedPerformancePayload,
    benchmark_monthly: PerformanceSeries,
) -> tuple[BenchmarkAlignmentPoint, ...]:
    """Create month-aligned portfolio/benchmark pairs as a correlation input hook."""

    if benchmark_monthly.frequency != "monthly":
        raise ValueError("benchmark alignment requires frequency='monthly'")

    benchmark = normalize_series(benchmark_monthly)
    portfolio_map = {point.as_of: point.value for point in normalized.monthly.points}
    benchmark_map = {point.as_of: point.value for point in benchmark.points}

    all_dates = sorted(set(portfolio_map) | set(benchmark_map))
    if not all_dates:
        return ()

    aligned: list[BenchmarkAlignmentPoint] = []
    for month_end in _iter_month_ends(all_dates[0], all_dates[-1]):
        portfolio_value = portfolio_map.get(month_end)
        benchmark_value = benchmark_map.get(month_end)
        if portfolio_value is None and benchmark_value is None:
            continue

        if portfolio_value is None:
            status: BenchmarkAlignmentStatus = "missing_portfolio"
        elif benchmark_value is None:
            status = "missing_benchmark"
        else:
            status = "aligned"

        aligned.append(
            BenchmarkAlignmentPoint(
                as_of=month_end,
                portfolio_value=portfolio_value,
                benchmark_value=benchmark_value,
                status=status,
            )
        )
    return tuple(aligned)


def correlation_inputs(
    alignment: tuple[BenchmarkAlignmentPoint, ...],
) -> tuple[tuple[date, float, float], ...]:
    """Extract aligned portfolio/benchmark month tuples for downstream correlation math."""

    return tuple(
        (point.as_of, point.portfolio_value, point.benchmark_value)
        for point in alignment
        if point.status == "aligned"
        and point.portfolio_value is not None
        and point.benchmark_value is not None
    )


def _build_canonical_months(
    monthly: PerformanceSeries,
    quarterly: PerformanceSeries | None,
    annual: PerformanceSeries | None,
) -> tuple[CanonicalMonthPoint, ...]:
    monthly_map = {point.as_of: point.value for point in monthly.points}
    quarterly_map = (
        {point.as_of: point.value for point in quarterly.points} if quarterly is not None else {}
    )
    annual_map = {point.as_of: point.value for point in annual.points} if annual is not None else {}

    start = monthly.points[0].as_of
    end = monthly.points[-1].as_of
    canonical: list[CanonicalMonthPoint] = []
    for month_end in _iter_month_ends(start, end):
        monthly_value = monthly_map.get(month_end)
        canonical.append(
            CanonicalMonthPoint(
                as_of=month_end,
                monthly_value=monthly_value,
                quarterly_value=quarterly_map.get(month_end),
                annual_value=annual_map.get(month_end),
                missing_month=monthly_value is None,
            )
        )
    return tuple(canonical)


def _normalizer_for_frequency(frequency: str) -> Callable[[date], date]:
    if frequency == "monthly":
        return _month_end
    if frequency == "quarterly":
        return _quarter_end
    if frequency == "annual":
        return _year_end
    raise ValueError(f"Unsupported frequency: {frequency}")


def _parse_date_value(raw_date: DateInput) -> date:
    if isinstance(raw_date, datetime):
        return raw_date.date()
    if isinstance(raw_date, date):
        return raw_date
    if not isinstance(raw_date, str):
        raise ValueError("Date input must be a date, datetime, or string")

    raw = raw_date.strip()
    if not raw:
        raise ValueError("Date input string must not be empty")

    parsers: tuple[Callable[[str], date], ...] = (
        date.fromisoformat,
        lambda v: datetime.strptime(v, "%Y/%m/%d").date(),
        lambda v: datetime.strptime(v, "%m/%d/%Y").date(),
        lambda v: datetime.strptime(v, "%Y%m%d").date(),
    )
    for parser in parsers:
        try:
            return parser(raw)
        except ValueError:
            continue

    raise ValueError(f"Unsupported date format: {raw_date!r}")


def _iter_month_ends(start: date, end: date) -> tuple[date, ...]:
    month_ends: list[date] = []
    cursor = _month_end(start)
    last = _month_end(end)
    while cursor <= last:
        month_ends.append(cursor)
        cursor = _next_month_end(cursor)
    return tuple(month_ends)


def _next_month_end(month_end: date) -> date:
    if month_end.month == 12:
        return date(month_end.year + 1, 1, 31)
    return _month_end(date(month_end.year, month_end.month + 1, 1))


def _month_end(day: date) -> date:
    if day.month == 12:
        return date(day.year, 12, 31)
    next_month_start = date(day.year, day.month + 1, 1)
    return next_month_start - timedelta(days=1)


def _quarter_end(day: date) -> date:
    quarter_end_month = ((day.month - 1) // 3 + 1) * 3
    return _month_end(date(day.year, quarter_end_month, 1))


def _year_end(day: date) -> date:
    return date(day.year, 12, 31)
