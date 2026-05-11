"""Aggregate visual-artifact feedback into tuning reports."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from statistics import mean

from inv_man_intake.contracts.image_feedback_contract import MAX_QUALITY_RANK, MIN_QUALITY_RANK
from inv_man_intake.data.provenance import VisualArtifactFeedbackRecord
from inv_man_intake.data.repository import VisualArtifactRepository


@dataclass(frozen=True)
class ArtifactFeedbackSummary:
    """Summary metrics for feedback attached to one visual artifact."""

    artifact_id: str
    feedback_count: int
    reviewer_count: int
    informative_count: int
    boilerplate_count: int
    informative_rate: float
    average_quality_rank: float
    quality_rank_distribution: dict[int, int]
    first_reviewed_at: str
    last_reviewed_at: str
    disagreement: bool


@dataclass(frozen=True)
class FeedbackSummaryReport:
    """Repository-wide feedback report for tuning workflows."""

    generated_at: str
    reviewed_from: str | None
    reviewed_to: str | None
    total_feedback_records: int
    unique_artifacts_reviewed: int
    reviewer_count: int
    informative_count: int
    boilerplate_count: int
    informative_rate: float
    average_quality_rank: float | None
    quality_rank_distribution: dict[int, int]
    first_reviewed_at: str | None
    last_reviewed_at: str | None
    multi_reviewer_artifact_count: int
    disagreement_artifact_count: int
    disagreement_rate: float
    artifacts: tuple[ArtifactFeedbackSummary, ...]


def generate_feedback_summary_report(
    repository: VisualArtifactRepository,
    *,
    generated_at: str,
    reviewed_from: str | None = None,
    reviewed_to: str | None = None,
) -> FeedbackSummaryReport:
    """Generate aggregate feedback metrics from persisted reviewer records."""

    records = repository.list_all_feedback(reviewed_from=reviewed_from, reviewed_to=reviewed_to)
    artifacts = _summarize_artifacts(records)
    informative_count = sum(1 for record in records if record.is_informative)
    boilerplate_count = len(records) - informative_count
    rank_distribution = _empty_rank_distribution()
    for record in records:
        rank_distribution[record.quality_rank] += 1

    multi_reviewer_artifact_count = sum(1 for artifact in artifacts if artifact.reviewer_count > 1)
    disagreement_artifact_count = sum(1 for artifact in artifacts if artifact.disagreement)

    return FeedbackSummaryReport(
        generated_at=generated_at,
        reviewed_from=reviewed_from,
        reviewed_to=reviewed_to,
        total_feedback_records=len(records),
        unique_artifacts_reviewed=len(artifacts),
        reviewer_count=len({record.reviewer for record in records}),
        informative_count=informative_count,
        boilerplate_count=boilerplate_count,
        informative_rate=_rate(informative_count, len(records)),
        average_quality_rank=_average_rank(records),
        quality_rank_distribution=rank_distribution,
        first_reviewed_at=records[0].reviewed_at if records else None,
        last_reviewed_at=records[-1].reviewed_at if records else None,
        multi_reviewer_artifact_count=multi_reviewer_artifact_count,
        disagreement_artifact_count=disagreement_artifact_count,
        disagreement_rate=_rate(disagreement_artifact_count, multi_reviewer_artifact_count),
        artifacts=artifacts,
    )


def render_feedback_summary_json(report: FeedbackSummaryReport) -> str:
    """Render a feedback report as stable JSON."""

    return json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n"


def render_feedback_summary_csv(report: FeedbackSummaryReport) -> str:
    """Render artifact-level feedback summary rows as CSV."""

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "artifact_id",
            "feedback_count",
            "reviewer_count",
            "informative_count",
            "boilerplate_count",
            "informative_rate",
            "average_quality_rank",
            "quality_rank_distribution",
            "first_reviewed_at",
            "last_reviewed_at",
            "disagreement",
        ],
    )
    writer.writeheader()
    for artifact in report.artifacts:
        writer.writerow(
            {
                "artifact_id": artifact.artifact_id,
                "feedback_count": artifact.feedback_count,
                "reviewer_count": artifact.reviewer_count,
                "informative_count": artifact.informative_count,
                "boilerplate_count": artifact.boilerplate_count,
                "informative_rate": f"{artifact.informative_rate:.4f}",
                "average_quality_rank": f"{artifact.average_quality_rank:.2f}",
                "quality_rank_distribution": json.dumps(
                    _rank_distribution_to_json(artifact.quality_rank_distribution),
                    sort_keys=True,
                ),
                "first_reviewed_at": artifact.first_reviewed_at,
                "last_reviewed_at": artifact.last_reviewed_at,
                "disagreement": "true" if artifact.disagreement else "false",
            }
        )
    return output.getvalue()


def _summarize_artifacts(
    records: tuple[VisualArtifactFeedbackRecord, ...],
) -> tuple[ArtifactFeedbackSummary, ...]:
    grouped: dict[str, list[VisualArtifactFeedbackRecord]] = {}
    for record in records:
        grouped.setdefault(record.artifact_id, []).append(record)

    summaries: list[ArtifactFeedbackSummary] = []
    for artifact_id in sorted(grouped):
        artifact_records = sorted(
            grouped[artifact_id], key=lambda item: (item.reviewed_at, item.reviewer)
        )
        informative_count = sum(1 for record in artifact_records if record.is_informative)
        boilerplate_count = len(artifact_records) - informative_count
        rank_distribution = _empty_rank_distribution()
        for record in artifact_records:
            rank_distribution[record.quality_rank] += 1
        ranks = [record.quality_rank for record in artifact_records]
        labels = {record.is_informative for record in artifact_records}
        disagreement = len(artifact_records) > 1 and (
            len(labels) > 1 or max(ranks) - min(ranks) >= 2
        )
        summaries.append(
            ArtifactFeedbackSummary(
                artifact_id=artifact_id,
                feedback_count=len(artifact_records),
                reviewer_count=len({record.reviewer for record in artifact_records}),
                informative_count=informative_count,
                boilerplate_count=boilerplate_count,
                informative_rate=_rate(informative_count, len(artifact_records)),
                average_quality_rank=mean(ranks),
                quality_rank_distribution=rank_distribution,
                first_reviewed_at=artifact_records[0].reviewed_at,
                last_reviewed_at=artifact_records[-1].reviewed_at,
                disagreement=disagreement,
            )
        )
    return tuple(summaries)


def _average_rank(records: tuple[VisualArtifactFeedbackRecord, ...]) -> float | None:
    if not records:
        return None
    return mean(record.quality_rank for record in records)


def _empty_rank_distribution() -> dict[int, int]:
    return dict.fromkeys(range(MIN_QUALITY_RANK, MAX_QUALITY_RANK + 1), 0)


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _rank_distribution_to_json(distribution: dict[int, int]) -> dict[str, int]:
    return {str(rank): count for rank, count in distribution.items()}


def _report_to_dict(report: FeedbackSummaryReport) -> dict[str, object]:
    return {
        "generated_at": report.generated_at,
        "reviewed_from": report.reviewed_from,
        "reviewed_to": report.reviewed_to,
        "summary": {
            "total_feedback_records": report.total_feedback_records,
            "unique_artifacts_reviewed": report.unique_artifacts_reviewed,
            "reviewer_count": report.reviewer_count,
            "informative_count": report.informative_count,
            "boilerplate_count": report.boilerplate_count,
            "informative_rate": report.informative_rate,
            "average_quality_rank": report.average_quality_rank,
            "quality_rank_distribution": _rank_distribution_to_json(
                report.quality_rank_distribution
            ),
            "first_reviewed_at": report.first_reviewed_at,
            "last_reviewed_at": report.last_reviewed_at,
            "multi_reviewer_artifact_count": report.multi_reviewer_artifact_count,
            "disagreement_artifact_count": report.disagreement_artifact_count,
            "disagreement_rate": report.disagreement_rate,
        },
        "artifacts": [
            {
                "artifact_id": artifact.artifact_id,
                "feedback_count": artifact.feedback_count,
                "reviewer_count": artifact.reviewer_count,
                "informative_count": artifact.informative_count,
                "boilerplate_count": artifact.boilerplate_count,
                "informative_rate": artifact.informative_rate,
                "average_quality_rank": artifact.average_quality_rank,
                "quality_rank_distribution": _rank_distribution_to_json(
                    artifact.quality_rank_distribution
                ),
                "first_reviewed_at": artifact.first_reviewed_at,
                "last_reviewed_at": artifact.last_reviewed_at,
                "disagreement": artifact.disagreement,
            }
            for artifact in report.artifacts
        ],
    }
