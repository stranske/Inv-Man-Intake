"""Tests for performance contract ingestion and validation."""

from __future__ import annotations

import pytest

from inv_man_intake.performance.ingest import load_document_timeseries, load_xlsx_timeseries

MONTHLY_MINIMAL = [
    {"frequency": "monthly", "as_of": "2025-01-31", "value": 1.2},
    {"frequency": "monthly", "as_of": "2025-02-28", "value": -0.4},
]


def test_monthly_series_is_required() -> None:
    rows = [{"frequency": "quarterly", "as_of": "2025-03-31", "value": 2.1}]

    with pytest.raises(ValueError) as exc:
        load_xlsx_timeseries(rows)

    assert str(exc.value) == "xlsx: monthly data is required and must contain at least one row"


def test_quarterly_and_annual_are_optional_but_accepted() -> None:
    rows = [
        *MONTHLY_MINIMAL,
        {"frequency": "quarterly", "as_of": "2025-03-31", "value": 3.0},
        {"frequency": "annual", "as_of": "2025-12-31", "value": 12.6},
    ]

    payload = load_xlsx_timeseries(rows)

    assert len(payload.monthly.points) == 2
    assert payload.quarterly is not None
    assert payload.annual is not None
    assert payload.quarterly.points[0].value == pytest.approx(3.0)
    assert payload.annual.points[0].value == pytest.approx(12.6)


def test_invalid_frequency_rejected_with_deterministic_error() -> None:
    rows = [{"frequency": "weekly", "as_of": "2025-01-31", "value": 1.0}]

    with pytest.raises(ValueError) as exc:
        load_xlsx_timeseries(rows)

    assert (
        str(exc.value)
        == "xlsx: rows[0].frequency must be one of monthly|quarterly|annual"
    )


def test_invalid_date_rejected_with_deterministic_error() -> None:
    rows = [{"frequency": "monthly", "as_of": "01/31/2025", "value": 1.0}]

    with pytest.raises(ValueError) as exc:
        load_document_timeseries(rows)

    assert str(exc.value) == "document: rows[0].as_of must use YYYY-MM-DD format"


def test_non_numeric_value_rejected_with_deterministic_error() -> None:
    rows = [{"frequency": "monthly", "as_of": "2025-01-31", "value": "bad"}]

    with pytest.raises(ValueError) as exc:
        load_document_timeseries(rows)

    assert str(exc.value) == "document: rows[0].value must be numeric"


def test_monthly_points_must_be_strictly_increasing() -> None:
    rows = [
        {"frequency": "monthly", "as_of": "2025-02-28", "value": 1.0},
        {"frequency": "monthly", "as_of": "2025-01-31", "value": 1.2},
    ]

    with pytest.raises(ValueError) as exc:
        load_xlsx_timeseries(rows)

    assert str(exc.value) == "monthly[1].as_of must be strictly increasing"
