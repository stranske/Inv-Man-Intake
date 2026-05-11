"""Aggregation logic for visual artifact feedback summary reports."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO

from inv_man_intake.data.provenance import VisualArtifactFeedbackRecord


@dataclass(frozen=True)
class FeedbackSummary:
    """Aggregated metrics from visual artifact feedback records."""

    generated_at: str
    timestamp_from: str | None
    timestamp_to: str | None
    total_feedback_records: int
    total_unique_artifacts: int
    informative_rate: float
    rank_distribution: dict[int, int]
    disagreement_rate: float


def aggregate_feedback(
    records: Sequence[VisualArtifactFeedbackRecord],
    timestamp_from: str | None = None,
    timestamp_to: str | None = None,
) -> FeedbackSummary:
    """Aggregate feedback records into summary metrics for tuning workflows.

    timestamp_from / timestamp_to are inclusive ISO-8601 UTC bounds applied to
    reviewed_at. Pass None to include all records on that side.
    """
    filtered: list[VisualArtifactFeedbackRecord] = []
    for r in records:
        if timestamp_from is not None and r.reviewed_at < timestamp_from:
            continue
        if timestamp_to is not None and r.reviewed_at > timestamp_to:
            continue
        filtered.append(r)

    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    total = len(filtered)

    if total == 0:
        return FeedbackSummary(
            generated_at=generated_at,
            timestamp_from=timestamp_from,
            timestamp_to=timestamp_to,
            total_feedback_records=0,
            total_unique_artifacts=0,
            informative_rate=0.0,
            rank_distribution={1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            disagreement_rate=0.0,
        )

    informative_count = sum(1 for r in filtered if r.is_informative)

    rank_distribution: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in filtered:
        rank_distribution[r.quality_rank] += 1

    # disagreement: artifact where reviewers hold conflicting is_informative opinions
    artifact_opinions: dict[str, set[bool]] = {}
    for r in filtered:
        artifact_opinions.setdefault(r.artifact_id, set()).add(r.is_informative)

    unique_artifacts = len(artifact_opinions)
    disagreement_count = sum(1 for opinions in artifact_opinions.values() if len(opinions) > 1)

    return FeedbackSummary(
        generated_at=generated_at,
        timestamp_from=timestamp_from,
        timestamp_to=timestamp_to,
        total_feedback_records=total,
        total_unique_artifacts=unique_artifacts,
        informative_rate=round(informative_count / total, 4),
        rank_distribution=rank_distribution,
        disagreement_rate=(
            round(disagreement_count / unique_artifacts, 4) if unique_artifacts else 0.0
        ),
    )


def render_json(summary: FeedbackSummary) -> str:
    """Serialise a FeedbackSummary to a JSON string."""
    payload = {
        "generated_at": summary.generated_at,
        "timestamp_from": summary.timestamp_from,
        "timestamp_to": summary.timestamp_to,
        "total_feedback_records": summary.total_feedback_records,
        "total_unique_artifacts": summary.total_unique_artifacts,
        "informative_rate": summary.informative_rate,
        "rank_distribution": {str(k): v for k, v in sorted(summary.rank_distribution.items())},
        "disagreement_rate": summary.disagreement_rate,
    }
    return json.dumps(payload, indent=2)


def render_csv(summary: FeedbackSummary) -> str:
    """Serialise a FeedbackSummary to a flat CSV string (one header row, one data row)."""
    buf = StringIO()
    writer = csv.writer(buf)
    rank_cols = {f"rank_{k}": v for k, v in sorted(summary.rank_distribution.items())}
    headers = [
        "generated_at",
        "timestamp_from",
        "timestamp_to",
        "total_feedback_records",
        "total_unique_artifacts",
        "informative_rate",
        *rank_cols.keys(),
        "disagreement_rate",
    ]
    values = [
        summary.generated_at,
        summary.timestamp_from or "",
        summary.timestamp_to or "",
        summary.total_feedback_records,
        summary.total_unique_artifacts,
        summary.informative_rate,
        *rank_cols.values(),
        summary.disagreement_rate,
    ]
    writer.writerow(headers)
    writer.writerow(values)
    return buf.getvalue()
