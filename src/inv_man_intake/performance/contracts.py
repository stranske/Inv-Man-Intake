"""Canonical performance time series contracts and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

Frequency = Literal["monthly", "quarterly", "annual"]


@dataclass(frozen=True)
class PerformancePoint:
    """Single dated performance value."""

    as_of: date
    value: float


@dataclass(frozen=True)
class PerformanceSeries:
    """A homogeneous frequency time series."""

    frequency: Frequency
    points: tuple[PerformancePoint, ...]


@dataclass(frozen=True)
class PerformancePayload:
    """Canonical ingest payload with required monthly data."""

    monthly: PerformanceSeries
    quarterly: PerformanceSeries | None = None
    annual: PerformanceSeries | None = None


def validate_series(series: PerformanceSeries) -> None:
    """Validate one frequency series and enforce deterministic ordering constraints."""

    if not series.points:
        raise ValueError(f"{series.frequency} series must contain at least one point")

    prev_day: date | None = None
    seen_days: set[date] = set()

    for idx, point in enumerate(series.points):
        if point.as_of in seen_days:
            raise ValueError(f"{series.frequency}[{idx}].as_of duplicates a previous date")
        seen_days.add(point.as_of)

        if prev_day is not None and point.as_of <= prev_day:
            raise ValueError(
                f"{series.frequency}[{idx}].as_of must be strictly increasing"
            )
        prev_day = point.as_of


def validate_payload(payload: PerformancePayload) -> None:
    """Validate the canonical payload shape and frequency handling rules."""

    if payload.monthly.frequency != "monthly":
        raise ValueError("monthly payload must use frequency='monthly'")
    validate_series(payload.monthly)

    if payload.quarterly is not None:
        if payload.quarterly.frequency != "quarterly":
            raise ValueError("quarterly payload must use frequency='quarterly'")
        validate_series(payload.quarterly)

    if payload.annual is not None:
        if payload.annual.frequency != "annual":
            raise ValueError("annual payload must use frequency='annual'")
        validate_series(payload.annual)
