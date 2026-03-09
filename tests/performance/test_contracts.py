from __future__ import annotations

from datetime import date

import pytest

from inv_man_intake.performance.contracts import (
    ANNUAL_SERIES_FIELD,
    MONTHLY_SERIES_FIELD,
    PERFORMANCE_SERIES_FIELDS,
    QUARTERLY_SERIES_FIELD,
    AnnualSeriesFieldDefinition,
    MonthlySeriesFieldDefinition,
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
    QuarterlySeriesFieldDefinition,
    validate_payload,
)


def test_frequency_field_definitions_are_explicit_and_ordered() -> None:
    assert isinstance(MONTHLY_SERIES_FIELD, MonthlySeriesFieldDefinition)
    assert MONTHLY_SERIES_FIELD.name == "monthly"
    assert MONTHLY_SERIES_FIELD.frequency == "monthly"
    assert MONTHLY_SERIES_FIELD.required is True

    assert isinstance(QUARTERLY_SERIES_FIELD, QuarterlySeriesFieldDefinition)
    assert QUARTERLY_SERIES_FIELD.name == "quarterly"
    assert QUARTERLY_SERIES_FIELD.frequency == "quarterly"
    assert QUARTERLY_SERIES_FIELD.required is False

    assert isinstance(ANNUAL_SERIES_FIELD, AnnualSeriesFieldDefinition)
    assert ANNUAL_SERIES_FIELD.name == "annual"
    assert ANNUAL_SERIES_FIELD.frequency == "annual"
    assert ANNUAL_SERIES_FIELD.required is False

    assert PERFORMANCE_SERIES_FIELDS == (
        MONTHLY_SERIES_FIELD,
        QUARTERLY_SERIES_FIELD,
        ANNUAL_SERIES_FIELD,
    )


def test_validate_payload_uses_field_definitions_for_frequency_checks() -> None:
    payload = PerformancePayload(
        monthly=PerformanceSeries(
            frequency="quarterly",
            points=(PerformancePoint(as_of=date(2025, 1, 31), value=1.0),),
        )
    )

    with pytest.raises(ValueError) as exc:
        validate_payload(payload)

    assert str(exc.value) == "monthly payload must use frequency='monthly'"
