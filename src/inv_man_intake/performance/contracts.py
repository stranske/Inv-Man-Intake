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


@dataclass(frozen=True)
class SeriesFieldDefinition:
    """Definition of one frequency field in the canonical payload."""

    name: str
    frequency: Frequency
    required: bool


@dataclass(frozen=True)
class MonthlySeriesFieldDefinition(SeriesFieldDefinition):
    """Field definition for required monthly data."""

    name: Literal["monthly"] = "monthly"
    frequency: Literal["monthly"] = "monthly"
    required: Literal[True] = True


@dataclass(frozen=True)
class QuarterlySeriesFieldDefinition(SeriesFieldDefinition):
    """Field definition for optional quarterly data."""

    name: Literal["quarterly"] = "quarterly"
    frequency: Literal["quarterly"] = "quarterly"
    required: Literal[False] = False


@dataclass(frozen=True)
class AnnualSeriesFieldDefinition(SeriesFieldDefinition):
    """Field definition for optional annual data."""

    name: Literal["annual"] = "annual"
    frequency: Literal["annual"] = "annual"
    required: Literal[False] = False


MONTHLY_SERIES_FIELD = MonthlySeriesFieldDefinition()
QUARTERLY_SERIES_FIELD = QuarterlySeriesFieldDefinition()
ANNUAL_SERIES_FIELD = AnnualSeriesFieldDefinition()

PERFORMANCE_SERIES_FIELDS: tuple[SeriesFieldDefinition, ...] = (
    MONTHLY_SERIES_FIELD,
    QUARTERLY_SERIES_FIELD,
    ANNUAL_SERIES_FIELD,
)


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
            raise ValueError(f"{series.frequency}[{idx}].as_of must be strictly increasing")
        prev_day = point.as_of


def validate_payload(payload: PerformancePayload) -> None:
    """Validate the canonical payload shape and frequency handling rules."""

    for field_def in PERFORMANCE_SERIES_FIELDS:
        series = getattr(payload, field_def.name)
        if series is None:
            if field_def.required:
                raise ValueError(f"{field_def.name} payload is required")
            continue

        if series.frequency != field_def.frequency:
            raise ValueError(f"{field_def.name} payload must use frequency='{field_def.frequency}'")
        validate_series(series)
