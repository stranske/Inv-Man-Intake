"""Tests for performance normalization and gap handling."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
)
from inv_man_intake.performance.normalize import (
    build_benchmark_alignment,
    canonical_date_string,
    correlation_inputs,
    describe_normalization_contract,
    detect_missing_months,
    normalize_date_input,
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


def test_detect_missing_months_normalizes_monthly_series_inputs() -> None:
    monthly = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 10), value=0.1),
            PerformancePoint(as_of=date(2025, 3, 4), value=0.2),
        ),
    )

    assert detect_missing_months(monthly) == (date(2025, 2, 28),)


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


@pytest.mark.parametrize(
    ("raw_date", "expected"),
    (
        (date(2025, 1, 15), date(2025, 1, 15)),
        (datetime(2025, 1, 15, 13, 45, 10), date(2025, 1, 15)),
        ("2025-01-15", date(2025, 1, 15)),
        ("2025/01/15", date(2025, 1, 15)),
        ("01/15/2025", date(2025, 1, 15)),
        ("20250115", date(2025, 1, 15)),
    ),
)
def test_normalize_date_input_supports_common_formats(raw_date: object, expected: date) -> None:
    assert normalize_date_input(raw_date) == expected


def test_normalize_date_input_applies_frequency_period_end_alignment() -> None:
    assert normalize_date_input("2025-02-01", frequency="monthly") == date(2025, 2, 28)
    assert normalize_date_input("2025-05-11", frequency="quarterly") == date(2025, 6, 30)
    assert normalize_date_input("2025-02-01", frequency="annual") == date(2025, 12, 31)
    assert canonical_date_string("2025-05-11", frequency="quarterly") == "2025-06-30"


def test_normalize_date_input_rejects_invalid_types_and_formats() -> None:
    with pytest.raises(ValueError) as exc:
        normalize_date_input("15-01-2025")
    assert str(exc.value) == "Unsupported date format: '15-01-2025'"

    with pytest.raises(ValueError) as exc:
        normalize_date_input(20250115)  # type: ignore[arg-type]
    assert str(exc.value) == "Date input must be a date, datetime, or string"


def test_describe_normalization_contract_is_stable_and_explicit() -> None:
    first = describe_normalization_contract()
    second = describe_normalization_contract()

    assert first == second
    assert "assumptions" in first
    assert "limitations" in first
    assert any("ISO 8601" in item for item in first["assumptions"])
    assert any("No interpolation" in item for item in first["limitations"])
