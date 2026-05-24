"""Tests for LangSmith fleet artifact records."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inv_man_intake.observability import langsmith_fleet


def test_build_fleet_records_use_inv_man_project_and_no_secret_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(langsmith_fleet.ENV_LANGSMITH_KEY, raising=False)
    context = langsmith_fleet.FleetRunContext(
        run_id="run-1",
        package_id="pkg_pdf_mixed_001",
        provider="pdf-primary",
        trace_id="trace-123",
    )
    summary = langsmith_fleet.IntakeFleetSummary(
        document_ids=("pkg_pdf_mixed_001:doc:0", "pkg_pdf_mixed_001:doc:1"),
        document_types=("pdf", "xlsx"),
        extraction_count=12,
        validation_status="escalated",
        redaction_status="redacted_metadata_only",
        confidence_state="escalated",
        escalation_state="ops_review",
        retry_count=1,
        score_count=5,
        review_queue_outcome="analyst",
        artifact_refs=("artifact:extraction/threshold-summary.json",),
        error_category="low_key_field_coverage",
    )

    records = langsmith_fleet.build_fleet_records(
        context=context,
        summary=summary,
        artifact_ref="artifact:langsmith-fleet.ndjson",
    )

    assert {record["operation"] for record in records} == {
        "package-intake",
        "document-extraction",
        "validation-escalation",
        "scoring-summary",
    }
    assert {record["status"] for record in records} == {"no_secret", "fallback"}
    assert all(record["schema_version"] == langsmith_fleet.SCHEMA_VERSION for record in records)
    assert all(record["repo"] == "stranske/Inv-Man-Intake" for record in records)
    assert all(record["surface"] == "intake-extraction" for record in records)
    assert all(record["github_issue"] == "stranske/Inv-Man-Intake#438" for record in records)
    assert all(record["domain"]["package_id"] == "pkg_pdf_mixed_001" for record in records)
    assert all(
        record["domain"]["redaction_status"] == "redacted_metadata_only" for record in records
    )
    assert all("raw" not in json.dumps(record).lower() for record in records)


def test_build_fleet_records_enable_langsmith_defaults_when_key_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(langsmith_fleet.ENV_LANGSMITH_KEY, "test-key")
    monkeypatch.delenv(langsmith_fleet.ENV_LANGCHAIN_TRACING_V2, raising=False)
    monkeypatch.delenv(langsmith_fleet.ENV_LANGCHAIN_API_KEY, raising=False)
    monkeypatch.delenv(langsmith_fleet.ENV_LANGCHAIN_PROJECT, raising=False)
    monkeypatch.delenv(langsmith_fleet.ENV_LANGSMITH_PROJECT, raising=False)

    records = langsmith_fleet.build_fleet_records(
        context=langsmith_fleet.FleetRunContext(
            run_id="run-1",
            package_id="pkg-1",
            trace_id="trace-123",
            trace_url="https://smith.langchain.com/r/trace-123",
        ),
        summary=langsmith_fleet.IntakeFleetSummary(
            document_ids=("doc-1",),
            document_types=("pdf",),
            extraction_count=2,
            validation_status="accepted",
            redaction_status="redacted_metadata_only",
            confidence_state="accepted",
            escalation_state="none",
            retry_count=0,
            score_count=5,
            review_queue_outcome="completed",
        ),
    )

    assert {record["status"] for record in records} == {"success"}
    assert records[0]["trace_id"] == "trace-123"
    assert records[0]["trace_url"] == "https://smith.langchain.com/r/trace-123"
    assert (
        langsmith_fleet.os.environ[langsmith_fleet.ENV_LANGCHAIN_PROJECT]
        == langsmith_fleet.DEFAULT_PROJECT
    )
    assert (
        langsmith_fleet.os.environ[langsmith_fleet.ENV_LANGSMITH_PROJECT]
        == langsmith_fleet.DEFAULT_PROJECT
    )
    assert langsmith_fleet.os.environ[langsmith_fleet.ENV_LANGCHAIN_TRACING_V2] == "true"
    assert langsmith_fleet.os.environ[langsmith_fleet.ENV_LANGCHAIN_API_KEY] == "test-key"


def test_write_fleet_records_emits_deterministic_ndjson(tmp_path: Path) -> None:
    path = tmp_path / langsmith_fleet.ARTIFACT_NAME
    records = [
        {
            "schema_version": langsmith_fleet.SCHEMA_VERSION,
            "repo": "stranske/Inv-Man-Intake",
            "surface": "intake-extraction",
            "operation": "package-intake",
            "run_id": "run-1",
            "status": "no_secret",
            "github_issue": "stranske/Inv-Man-Intake#438",
            "domain": {
                "package_id": "pkg-1",
                "document_count": 1,
                "document_ids": ["doc-1"],
                "document_types": ["pdf"],
                "redaction_status": "redacted_metadata_only",
                "validation_status": "accepted",
                "error_category": "none",
            },
        }
    ]

    langsmith_fleet.write_fleet_records(path, records)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == records[0]
