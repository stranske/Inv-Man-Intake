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
        trace_refs=("trace:trace-123",),
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
    assert all(record["domain"]["document_id"] == "pkg_pdf_mixed_001:doc:0" for record in records)
    assert all(record["domain"]["trace_refs"] == ["trace:trace-123"] for record in records)
    assert all(
        record["domain"]["redaction_status"] == "redacted_metadata_only" for record in records
    )
    assert all(record["domain"]["extraction_count"] == 12 for record in records)
    assert all(record["domain"]["validation_status"] == "escalated" for record in records)
    assert all(record["domain"]["confidence_state"] == "escalated" for record in records)
    assert all(record["domain"]["escalation_state"] == "ops_review" for record in records)
    assert all(record["domain"]["retry_count"] == 1 for record in records)
    assert all(record["domain"]["score_count"] == 5 for record in records)
    assert all(record["domain"]["review_queue_outcome"] == "analyst" for record in records)
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
            trace_refs=("trace:trace-123",),
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


def test_derive_trace_url_returns_none_for_empty_values() -> None:
    assert langsmith_fleet.derive_trace_url(None) is None
    assert langsmith_fleet.derive_trace_url("  ") is None


def test_derive_trace_url_builds_clickable_url() -> None:
    assert (
        langsmith_fleet.derive_trace_url("trace-123") == "https://smith.langchain.com/r/trace-123"
    )


def _valid_record_for(operation: str = "package-intake") -> dict[str, object]:
    return {
        "schema_version": langsmith_fleet.SCHEMA_VERSION,
        "repo": "stranske/Inv-Man-Intake",
        "surface": "intake-extraction",
        "operation": operation,
        "run_id": "run-1",
        "status": "no_secret",
        "github_issue": "stranske/Inv-Man-Intake#438",
        "recorded_at": "2026-05-24T11:00:00Z",
        "error_category": "none",
        "domain": {
            "package_id": "pkg-1",
            "document_id": "doc-1",
            "correlation_id": "corr-1",
            "document_count": 1,
            "document_ids": ["doc-1"],
            "document_types": ["pdf"],
            "redaction_status": "redacted_metadata_only",
            "trace_refs": ["trace:trace-123"],
            "validation_status": "accepted",
            "extraction_count": 1,
            "confidence_state": "accepted",
            "escalation_state": "none",
            "retry_count": 0,
            "score_count": 1,
            "review_queue_outcome": "none",
        },
    }


def test_write_fleet_records_emits_deterministic_ndjson(tmp_path: Path) -> None:
    path = tmp_path / langsmith_fleet.ARTIFACT_NAME
    records = [_valid_record_for()]

    langsmith_fleet.write_fleet_records(path, records)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == records[0]


def test_validate_fleet_records_accepts_full_contract() -> None:
    langsmith_fleet.validate_fleet_records([_valid_record_for()])


def test_validate_fleet_records_rejects_missing_top_level_field() -> None:
    record = _valid_record_for()
    del record["error_category"]
    with pytest.raises(ValueError, match="missing top-level fields.*error_category"):
        langsmith_fleet.validate_fleet_records([record])


def test_validate_fleet_records_rejects_missing_domain_field() -> None:
    record = _valid_record_for()
    del record["domain"]["package_id"]
    with pytest.raises(ValueError, match="missing domain fields.*package_id"):
        langsmith_fleet.validate_fleet_records([record])


def test_validate_fleet_records_rejects_invalid_status() -> None:
    record = _valid_record_for()
    record["status"] = "exploded"
    with pytest.raises(ValueError, match="invalid status"):
        langsmith_fleet.validate_fleet_records([record])


@pytest.mark.parametrize(
    "bad_ref",
    [
        "/etc/passwd",
        "artifact:/etc/passwd",
        "artifact:..\\\\windows\\\\system32",
        "artifact:C:/Users/foo.json",
        "artifact:../outside/secret.json",
        "artifact:",
        "report-root/foo.json",
    ],
)
def test_validate_fleet_records_rejects_unsafe_artifact_ref(bad_ref: str) -> None:
    record = _valid_record_for()
    record["artifact_ref"] = bad_ref
    with pytest.raises(ValueError, match="artifact_ref"):
        langsmith_fleet.validate_fleet_records([record])


def test_validate_fleet_records_rejects_unsafe_artifact_in_domain_list() -> None:
    record = _valid_record_for()
    record["domain"]["artifact_refs"] = ["artifact:/etc/passwd"]
    with pytest.raises(ValueError, match="artifact_refs"):
        langsmith_fleet.validate_fleet_records([record])


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "document_text",
        "raw_document",
        "extracted_value",
        "model_output",
        "api_key",
        "ssn",
        "pii_fields",
    ],
)
def test_validate_fleet_records_rejects_sensitive_payload_field(sensitive_key: str) -> None:
    record = _valid_record_for()
    record["domain"][sensitive_key] = "redacted"
    with pytest.raises(ValueError, match="sensitive field"):
        langsmith_fleet.validate_fleet_records([record])


def test_build_fleet_records_emits_top_level_error_category_and_latency_ms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(langsmith_fleet.ENV_LANGSMITH_KEY, raising=False)
    context = langsmith_fleet.FleetRunContext(
        run_id="run-1",
        package_id="pkg-1",
        latency_ms=1234,
    )
    summary = langsmith_fleet.IntakeFleetSummary(
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
        trace_refs=("trace:trace-123",),
        error_category="low_key_field_coverage",
    )

    records = langsmith_fleet.build_fleet_records(context=context, summary=summary)

    assert all(record["error_category"] == "low_key_field_coverage" for record in records)
    assert all(record["latency_ms"] == 1234 for record in records)


def test_write_fleet_records_rejects_records_with_unsafe_artifact_ref(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    path = artifact_dir / langsmith_fleet.ARTIFACT_NAME
    record = _valid_record_for()
    record["artifact_ref"] = "artifact:/etc/passwd"
    with pytest.raises(ValueError, match="artifact_ref"):
        langsmith_fleet.write_fleet_records(path, [record])
    assert not path.exists()
    assert not artifact_dir.exists()
