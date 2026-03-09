"""Ingestion loaders and validation for performance time series."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import cast

from inv_man_intake.performance.contracts import (
    Frequency,
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
    validate_payload,
)


def load_xlsx_timeseries(rows: Sequence[Mapping[str, object]]) -> PerformancePayload:
    """Load canonical payload from XLSX-derived rows.

    Expected keys per row:
    - frequency: monthly|quarterly|annual
    - as_of: ISO date string (YYYY-MM-DD)
    - value: numeric (int or float)
    """

    return _load_rows(rows, source="xlsx")


def load_document_timeseries(rows: Sequence[Mapping[str, object]]) -> PerformancePayload:
    """Load canonical payload from document-derived extraction rows."""

    return _load_rows(rows, source="document")


def _load_rows(rows: Sequence[Mapping[str, object]], *, source: str) -> PerformancePayload:
    grouped: dict[Frequency, list[PerformancePoint]] = {
        "monthly": [],
        "quarterly": [],
        "annual": [],
    }

    for idx, row in enumerate(rows):
        freq = _parse_frequency(row.get("frequency"), source=source, idx=idx)
        point = _parse_point(row, source=source, idx=idx)
        grouped[freq].append(point)

    if not grouped["monthly"]:
        raise ValueError(f"{source}: monthly data is required and must contain at least one row")

    payload = PerformancePayload(
        monthly=PerformanceSeries("monthly", tuple(grouped["monthly"])),
        quarterly=(
            PerformanceSeries("quarterly", tuple(grouped["quarterly"]))
            if grouped["quarterly"]
            else None
        ),
        annual=(
            PerformanceSeries("annual", tuple(grouped["annual"])) if grouped["annual"] else None
        ),
    )
    validate_payload(payload)
    return payload


def _parse_frequency(value: object, *, source: str, idx: int) -> Frequency:
    if not isinstance(value, str):
        raise ValueError(f"{source}: rows[{idx}].frequency must be a string")

    normalized = value.strip().lower()
    if normalized not in {"monthly", "quarterly", "annual"}:
        raise ValueError(f"{source}: rows[{idx}].frequency must be one of monthly|quarterly|annual")
    return cast(Frequency, normalized)


def _parse_point(row: Mapping[str, object], *, source: str, idx: int) -> PerformancePoint:
    raw_as_of = row.get("as_of")
    if not isinstance(raw_as_of, str):
        raise ValueError(f"{source}: rows[{idx}].as_of must be an ISO date string")

    try:
        as_of = date.fromisoformat(raw_as_of)
    except ValueError as exc:
        raise ValueError(f"{source}: rows[{idx}].as_of must use YYYY-MM-DD format") from exc

    raw_value = row.get("value")
    if isinstance(raw_value, bool):
        raise ValueError(f"{source}: rows[{idx}].value must be numeric")
    if not isinstance(raw_value, int | float):
        raise ValueError(f"{source}: rows[{idx}].value must be numeric")

    return PerformancePoint(as_of=as_of, value=float(raw_value))
