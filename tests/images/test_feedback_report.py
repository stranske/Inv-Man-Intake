"""Tests for visual-artifact feedback summary exports."""

from __future__ import annotations

import json
import sqlite3

from inv_man_intake.contracts.image_feedback_contract import ImageFeedbackRecord
from inv_man_intake.data.migrations.core_schema import apply_core_schema
from inv_man_intake.data.provenance import VisualArtifactRecord
from inv_man_intake.data.repository import VisualArtifactRepository
from inv_man_intake.images.feedback_report import (
    feedback_summary_metric_definitions,
    generate_feedback_summary_report,
    render_feedback_summary_csv,
    render_feedback_summary_json,
)
from inv_man_intake.images.feedback_service import VisualArtifactFeedbackService


def _repository() -> VisualArtifactRepository:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_core_schema(conn)
    conn.execute(
        "INSERT INTO firms (firm_id, legal_name, aliases_json, created_at) VALUES (?, ?, ?, ?)",
        ("firm_1", "Alpha Capital", None, "2026-03-01T08:00:00Z"),
    )
    conn.execute(
        (
            "INSERT INTO funds (fund_id, firm_id, fund_name, strategy, asset_class, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)"
        ),
        (
            "fund_1",
            "firm_1",
            "Alpha Fund",
            "market_neutral",
            "equity_market_neutral",
            "2026-03-01T08:30:00Z",
        ),
    )
    conn.execute(
        (
            "INSERT INTO documents (document_id, fund_id, file_name, file_hash, received_at, "
            "version_date, source_channel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            "doc_1",
            "fund_1",
            "manager_deck.pdf",
            "hash_doc_1",
            "2026-03-01T09:00:00Z",
            "2026-03-01",
            "email",
            "2026-03-01T09:00:00Z",
        ),
    )
    conn.commit()
    repo = VisualArtifactRepository(conn)
    repo.ensure_schema()
    for artifact_id, page in (("va_1", 2), ("va_2", 3)):
        repo.insert_artifact(
            VisualArtifactRecord(
                artifact_id=artifact_id,
                document_id="doc_1",
                source_type="pdf",
                source_page=page,
                source_slide=None,
                source_ref=f"pdf-object-{page}",
                storage_path=f"artifacts/doc_1/pdf/page-{page}/object.bin",
                sha256=f"hash-{artifact_id}",
                mime_type="image/jpeg",
                byte_size=1240,
                extracted_at="2026-03-01T09:10:00Z",
            )
        )
    repo.ensure_feedback_schema()
    return repo


def test_feedback_summary_report_calculates_metrics_and_disagreement() -> None:
    repo = _repository()
    service = VisualArtifactFeedbackService(repo)
    for record in (
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=5,
            reviewer="analyst-a",
            timestamp="2026-03-01T10:00:00Z",
        ),
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=False,
            quality_rank=2,
            reviewer="analyst-b",
            timestamp="2026-03-01T10:05:00Z",
        ),
        ImageFeedbackRecord(
            artifact_id="va_2",
            is_informative=True,
            quality_rank=4,
            reviewer="analyst-a",
            timestamp="2026-03-01T11:00:00Z",
        ),
    ):
        service.record_feedback(record)

    report = generate_feedback_summary_report(repo, generated_at="2026-03-01T12:00:00Z")

    assert report.total_feedback_records == 3
    assert report.unique_artifacts_reviewed == 2
    assert report.reviewer_count == 2
    assert report.informative_rate == 2 / 3
    assert report.quality_rank_distribution == {1: 0, 2: 1, 3: 0, 4: 1, 5: 1}
    assert report.first_reviewed_at == "2026-03-01T10:00:00Z"
    assert report.last_reviewed_at == "2026-03-01T11:00:00Z"
    assert report.multi_reviewer_artifact_count == 1
    assert report.disagreement_artifact_count == 1
    assert report.disagreement_rate == 1.0
    assert report.artifacts[0].artifact_id == "va_1"
    assert report.artifacts[0].disagreement is True


def test_feedback_summary_filters_by_review_timestamp_and_renders_exports() -> None:
    repo = _repository()
    service = VisualArtifactFeedbackService(repo)
    service.record_feedback(
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=5,
            reviewer="analyst-a",
            timestamp="2026-03-01T09:59:00Z",
        )
    )
    service.record_feedback(
        ImageFeedbackRecord(
            artifact_id="va_2",
            is_informative=False,
            quality_rank=1,
            reviewer="analyst-b",
            timestamp="2026-03-01T10:30:00Z",
        )
    )

    report = generate_feedback_summary_report(
        repo,
        generated_at="2026-03-01T12:00:00Z",
        reviewed_from="2026-03-01T10:00:00Z",
        reviewed_to="2026-03-01T11:00:00Z",
    )

    payload = json.loads(render_feedback_summary_json(report))
    csv_payload = render_feedback_summary_csv(report)

    assert payload["summary"]["total_feedback_records"] == 1
    assert payload["summary"]["quality_rank_distribution"]["1"] == 1
    assert payload["artifacts"][0]["artifact_id"] == "va_2"
    assert "artifact_id,feedback_count,reviewer_count" in csv_payload
    assert "va_2,1,1,0,1,0.0000,1.00" in csv_payload


def test_feedback_summary_metric_definitions_cover_required_summary_metrics() -> None:
    definitions = feedback_summary_metric_definitions()
    by_key = {definition.key: definition for definition in definitions}

    assert tuple(by_key) == (
        "informative_rate",
        "quality_rank_distribution",
        "disagreement_rate",
    )
    assert by_key["informative_rate"].formula == "informative_count / feedback_count"
    assert by_key["quality_rank_distribution"].level == "report,artifact"
    assert (
        by_key["disagreement_rate"].formula
        == "disagreement_artifact_count / multi_reviewer_artifact_count"
    )


def test_feedback_summary_aggregation_on_synthetic_dataset() -> None:
    repo = _repository()
    service = VisualArtifactFeedbackService(repo)
    repo.insert_artifact(
        VisualArtifactRecord(
            artifact_id="va_3",
            document_id="doc_1",
            source_type="pdf",
            source_page=4,
            source_slide=None,
            source_ref="pdf-object-4",
            storage_path="artifacts/doc_1/pdf/page-4/object.bin",
            sha256="hash-va_3",
            mime_type="image/jpeg",
            byte_size=1440,
            extracted_at="2026-03-01T09:20:00Z",
        )
    )

    for record in (
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=4,
            reviewer="analyst-a",
            timestamp="2026-03-01T10:00:00Z",
        ),
        ImageFeedbackRecord(
            artifact_id="va_1",
            is_informative=True,
            quality_rank=5,
            reviewer="analyst-b",
            timestamp="2026-03-01T10:01:00Z",
        ),
        ImageFeedbackRecord(
            artifact_id="va_2",
            is_informative=False,
            quality_rank=2,
            reviewer="analyst-a",
            timestamp="2026-03-01T10:02:00Z",
        ),
        ImageFeedbackRecord(
            artifact_id="va_2",
            is_informative=False,
            quality_rank=3,
            reviewer="analyst-b",
            timestamp="2026-03-01T10:03:00Z",
        ),
        ImageFeedbackRecord(
            artifact_id="va_3",
            is_informative=True,
            quality_rank=1,
            reviewer="analyst-c",
            timestamp="2026-03-01T10:04:00Z",
        ),
    ):
        service.record_feedback(record)

    report = generate_feedback_summary_report(repo, generated_at="2026-03-01T12:00:00Z")

    assert report.total_feedback_records == 5
    assert report.unique_artifacts_reviewed == 3
    assert report.reviewer_count == 3
    assert report.informative_count == 3
    assert report.boilerplate_count == 2
    assert report.informative_rate == 3 / 5
    assert report.quality_rank_distribution == {1: 1, 2: 1, 3: 1, 4: 1, 5: 1}
    assert report.multi_reviewer_artifact_count == 2
    assert report.disagreement_artifact_count == 0
    assert report.disagreement_rate == 0.0
