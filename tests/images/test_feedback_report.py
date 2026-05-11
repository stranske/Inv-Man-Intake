"""Tests for image feedback summary aggregation (issue #27)."""

from __future__ import annotations

import json

from inv_man_intake.data.provenance import VisualArtifactFeedbackRecord
from inv_man_intake.images.report import (
    aggregate_feedback,
    render_csv,
    render_json,
)


def _record(
    artifact_id: str,
    reviewer: str,
    *,
    is_informative: bool = True,
    quality_rank: int = 4,
    reviewed_at: str = "2026-03-01T10:00:00Z",
    notes: str | None = None,
) -> VisualArtifactFeedbackRecord:
    return VisualArtifactFeedbackRecord(
        artifact_id=artifact_id,
        is_informative=is_informative,
        quality_rank=quality_rank,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        notes=notes,
    )


def test_empty_records_returns_zero_metrics() -> None:
    summary = aggregate_feedback([])

    assert summary.total_feedback_records == 0
    assert summary.total_unique_artifacts == 0
    assert summary.informative_rate == 0.0
    assert summary.disagreement_rate == 0.0
    assert summary.rank_distribution == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    assert summary.timestamp_from is None
    assert summary.timestamp_to is None


def test_single_informative_record_gives_full_informative_rate() -> None:
    records = [_record("va_1", "analyst-a", is_informative=True, quality_rank=5)]
    summary = aggregate_feedback(records)

    assert summary.total_feedback_records == 1
    assert summary.total_unique_artifacts == 1
    assert summary.informative_rate == 1.0
    assert summary.rank_distribution == {1: 0, 2: 0, 3: 0, 4: 0, 5: 1}
    assert summary.disagreement_rate == 0.0


def test_single_boilerplate_record_gives_zero_informative_rate() -> None:
    records = [_record("va_1", "analyst-a", is_informative=False, quality_rank=2)]
    summary = aggregate_feedback(records)

    assert summary.informative_rate == 0.0
    assert summary.rank_distribution[2] == 1


def test_mixed_informative_rate_rounds_to_four_decimal_places() -> None:
    records = [
        _record("va_1", "analyst-a", is_informative=True),
        _record("va_2", "analyst-a", is_informative=False),
        _record("va_3", "analyst-a", is_informative=True),
    ]
    summary = aggregate_feedback(records)

    assert summary.total_feedback_records == 3
    assert summary.total_unique_artifacts == 3
    assert summary.informative_rate == round(2 / 3, 4)


def test_rank_distribution_counts_each_rank_correctly() -> None:
    records = [
        _record("va_1", "analyst-a", quality_rank=1),
        _record("va_2", "analyst-a", quality_rank=2),
        _record("va_3", "analyst-a", quality_rank=3),
        _record("va_4", "analyst-a", quality_rank=3),
        _record("va_5", "analyst-a", quality_rank=5),
    ]
    summary = aggregate_feedback(records)

    assert summary.rank_distribution == {1: 1, 2: 1, 3: 2, 4: 0, 5: 1}


def test_disagreement_rate_zero_when_reviewers_agree() -> None:
    records = [
        _record("va_1", "analyst-a", is_informative=True),
        _record("va_1", "analyst-b", is_informative=True),
    ]
    summary = aggregate_feedback(records)

    assert summary.total_feedback_records == 2
    assert summary.total_unique_artifacts == 1
    assert summary.disagreement_rate == 0.0


def test_disagreement_rate_is_one_when_all_artifacts_have_conflicting_reviews() -> None:
    records = [
        _record("va_1", "analyst-a", is_informative=True),
        _record("va_1", "analyst-b", is_informative=False),
        _record("va_2", "analyst-a", is_informative=False),
        _record("va_2", "analyst-b", is_informative=True),
    ]
    summary = aggregate_feedback(records)

    assert summary.total_unique_artifacts == 2
    assert summary.disagreement_rate == 1.0


def test_disagreement_rate_partial_conflict() -> None:
    records = [
        _record("va_1", "analyst-a", is_informative=True),
        _record("va_1", "analyst-b", is_informative=False),  # disagree
        _record("va_2", "analyst-a", is_informative=True),
        _record("va_2", "analyst-b", is_informative=True),  # agree
    ]
    summary = aggregate_feedback(records)

    assert summary.disagreement_rate == 0.5


def test_timestamp_filter_from_excludes_earlier_records() -> None:
    records = [
        _record("va_1", "analyst-a", reviewed_at="2026-01-01T00:00:00Z"),
        _record("va_2", "analyst-a", reviewed_at="2026-03-01T00:00:00Z"),
        _record("va_3", "analyst-a", reviewed_at="2026-06-01T00:00:00Z"),
    ]
    summary = aggregate_feedback(records, timestamp_from="2026-03-01T00:00:00Z")

    assert summary.total_feedback_records == 2
    assert summary.timestamp_from == "2026-03-01T00:00:00Z"


def test_timestamp_filter_to_excludes_later_records() -> None:
    records = [
        _record("va_1", "analyst-a", reviewed_at="2026-01-01T00:00:00Z"),
        _record("va_2", "analyst-a", reviewed_at="2026-03-01T00:00:00Z"),
        _record("va_3", "analyst-a", reviewed_at="2026-06-01T00:00:00Z"),
    ]
    summary = aggregate_feedback(records, timestamp_to="2026-03-01T00:00:00Z")

    assert summary.total_feedback_records == 2
    assert summary.timestamp_to == "2026-03-01T00:00:00Z"


def test_timestamp_filter_range_retains_only_records_within_bounds() -> None:
    records = [
        _record("va_1", "analyst-a", reviewed_at="2026-01-01T00:00:00Z"),
        _record("va_2", "analyst-a", reviewed_at="2026-03-01T12:00:00Z"),
        _record("va_3", "analyst-a", reviewed_at="2026-06-01T00:00:00Z"),
    ]
    summary = aggregate_feedback(
        records,
        timestamp_from="2026-02-01T00:00:00Z",
        timestamp_to="2026-04-01T00:00:00Z",
    )

    assert summary.total_feedback_records == 1
    assert summary.total_unique_artifacts == 1


def test_render_json_produces_valid_json_with_all_fields() -> None:
    summary = aggregate_feedback(
        [_record("va_1", "analyst-a", is_informative=True, quality_rank=4)]
    )
    rendered = render_json(summary)
    data = json.loads(rendered)

    assert data["total_feedback_records"] == 1
    assert data["informative_rate"] == 1.0
    assert data["disagreement_rate"] == 0.0
    assert "rank_distribution" in data
    assert data["rank_distribution"]["4"] == 1
    assert "generated_at" in data


def test_render_csv_produces_header_and_data_row() -> None:
    summary = aggregate_feedback(
        [
            _record("va_1", "analyst-a", is_informative=True, quality_rank=3),
            _record("va_2", "analyst-a", is_informative=False, quality_rank=2),
        ]
    )
    rendered = render_csv(summary)
    lines = [line for line in rendered.strip().splitlines() if line]

    assert len(lines) == 2
    header = lines[0]
    assert "informative_rate" in header
    assert "disagreement_rate" in header
    assert "rank_3" in header


def test_render_csv_data_row_values_are_correct() -> None:
    records = [_record("va_1", "analyst-a", is_informative=True, quality_rank=5)]
    summary = aggregate_feedback(records)
    rendered = render_csv(summary)
    lines = rendered.strip().splitlines()
    headers = lines[0].split(",")
    values = lines[1].split(",")
    data = dict(zip(headers, values, strict=False))

    assert data["total_feedback_records"] == "1"
    assert data["informative_rate"] == "1.0"
    assert data["rank_5"] == "1"


def test_generated_at_is_present_and_utc_formatted() -> None:
    summary = aggregate_feedback([])

    assert summary.generated_at.endswith("Z")
    assert "T" in summary.generated_at


def test_multiple_reviewers_per_artifact_are_counted_as_one_artifact() -> None:
    records = [
        _record("va_1", "analyst-a"),
        _record("va_1", "analyst-b"),
        _record("va_1", "analyst-c"),
    ]
    summary = aggregate_feedback(records)

    assert summary.total_feedback_records == 3
    assert summary.total_unique_artifacts == 1
