"""Build dashboard-safe LangSmith fleet records for intake and extraction runs."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Literal

SCHEMA_VERSION: Final = "langsmith-fleet/v1"
REPO: Final = "stranske/Inv-Man-Intake"
SURFACE: Final = "intake-extraction"
GITHUB_ISSUE: Final = "stranske/Inv-Man-Intake#438"
ARTIFACT_NAME: Final = "langsmith-fleet.ndjson"
DEFAULT_PROJECT: Final = "inv-man-intake"
ENV_LANGSMITH_KEY: Final = "LANGSMITH_API_KEY"
ENV_LANGCHAIN_PROJECT: Final = "LANGCHAIN_PROJECT"
ENV_LANGSMITH_PROJECT: Final = "LANGSMITH_PROJECT"
ENV_LANGCHAIN_TRACING_V2: Final = "LANGCHAIN_TRACING_V2"
ENV_LANGCHAIN_API_KEY: Final = "LANGCHAIN_API_KEY"

Status = Literal["success", "error", "fallback", "no_secret", "skipped"]


@dataclass(frozen=True)
class FleetRunContext:
    """Shared metadata for an intake package run."""

    run_id: str
    package_id: str
    provider: str | None = None
    model: str | None = None
    trace_id: str | None = None
    trace_url: str | None = None
    recorded_at: str | None = None
    github_pr: str | None = None


@dataclass(frozen=True)
class IntakeFleetSummary:
    """Dashboard-safe summary of a package intake/extraction pipeline run."""

    document_ids: tuple[str, ...]
    document_types: tuple[str, ...]
    extraction_count: int
    validation_status: str
    redaction_status: str
    confidence_state: str
    escalation_state: str
    retry_count: int
    score_count: int
    review_queue_outcome: str
    artifact_refs: tuple[str, ...] = ()
    error_category: str | None = None


def ensure_langsmith_project_defaults(env: Mapping[str, str] | None = None) -> bool:
    """Apply Inv-Man-Intake LangSmith defaults when a key is present."""

    if env is not None and env is not os.environ:
        return bool(env.get(ENV_LANGSMITH_KEY, "").strip())
    api_key = os.environ.get(ENV_LANGSMITH_KEY, "").strip()
    if not api_key:
        return False
    os.environ.setdefault(ENV_LANGCHAIN_TRACING_V2, "true")
    os.environ.setdefault(ENV_LANGCHAIN_PROJECT, DEFAULT_PROJECT)
    os.environ.setdefault(ENV_LANGSMITH_PROJECT, DEFAULT_PROJECT)
    os.environ.setdefault(ENV_LANGCHAIN_API_KEY, api_key)
    return True


def build_fleet_records(
    *,
    context: FleetRunContext,
    summary: IntakeFleetSummary,
    artifact_ref: str | None = None,
) -> list[dict[str, Any]]:
    """Return Workflows-compatible records for the major intake pipeline stages."""

    tracing_enabled = ensure_langsmith_project_defaults()
    base_status: Status = "success" if tracing_enabled else "no_secret"
    recorded_at = context.recorded_at or _utc_timestamp()
    shared_domain = _shared_domain(context=context, summary=summary)
    return [
        _record(
            context=context,
            operation="package-intake",
            status=base_status,
            recorded_at=recorded_at,
            domain={
                **shared_domain,
                "stage_status": "accepted",
                "artifact_refs": list(summary.artifact_refs),
            },
            artifact_ref=artifact_ref,
        ),
        _record(
            context=context,
            operation="document-extraction",
            status=_extraction_status(base_status, summary),
            recorded_at=recorded_at,
            domain={
                **shared_domain,
                "extraction_count": summary.extraction_count,
                "confidence_state": summary.confidence_state,
                "retry_count": summary.retry_count,
            },
            artifact_ref=artifact_ref,
        ),
        _record(
            context=context,
            operation="validation-escalation",
            status=base_status if summary.validation_status != "error" else "error",
            recorded_at=recorded_at,
            domain={
                **shared_domain,
                "validation_status": summary.validation_status,
                "escalation_state": summary.escalation_state,
                "review_queue_outcome": summary.review_queue_outcome,
            },
            artifact_ref=artifact_ref,
        ),
        _record(
            context=context,
            operation="scoring-summary",
            status=base_status,
            recorded_at=recorded_at,
            domain={
                **shared_domain,
                "score_count": summary.score_count,
                "review_queue_outcome": summary.review_queue_outcome,
            },
            artifact_ref=artifact_ref,
        ),
    ]


def build_summary_from_pipeline(
    *,
    document_ids: Iterable[str],
    extraction: object,
    secondary_extraction: object,
    validation_status: str,
    score_count: int,
    review_queue_outcome: str,
    artifact_refs: Iterable[str] = (),
) -> IntakeFleetSummary:
    """Create dashboard-safe domain metadata from pipeline outputs."""

    extraction_fields = tuple(getattr(extraction, "fields", ()))
    confidence_escalation = _field_value(extraction_fields, "confidence.document.escalation")
    escalation_reason = _field_value(extraction_fields, "confidence.document.escalation_reason")
    secondary_retry_count = getattr(secondary_extraction, "retry_count", 0)
    secondary_route = getattr(secondary_extraction, "escalation_route", None)
    return IntakeFleetSummary(
        document_ids=tuple(str(item) for item in document_ids),
        document_types=("pdf", "xlsx", "unsupported"),
        extraction_count=len(extraction_fields),
        validation_status=validation_status,
        redaction_status="redacted_metadata_only",
        confidence_state="escalated" if confidence_escalation is True else "accepted",
        escalation_state=str(secondary_route or escalation_reason or "none"),
        retry_count=int(secondary_retry_count or 0),
        score_count=score_count,
        review_queue_outcome=review_queue_outcome,
        artifact_refs=tuple(sorted(str(item) for item in artifact_refs if str(item).strip())),
        error_category=str(escalation_reason) if escalation_reason else None,
    )


def write_fleet_records(path: Path, records: Iterable[Mapping[str, Any]]) -> Path:
    """Write records as deterministic NDJSON and return the artifact path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(dict(record), sort_keys=True, separators=(",", ":")) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def _shared_domain(
    *, context: FleetRunContext, summary: IntakeFleetSummary
) -> dict[str, Any]:
    return {
        "package_id": context.package_id,
        "document_count": len(summary.document_ids),
        "document_ids": list(summary.document_ids),
        "document_types": list(summary.document_types),
        "redaction_status": summary.redaction_status,
        "validation_status": summary.validation_status,
        "error_category": summary.error_category or "none",
    }


def _record(
    *,
    context: FleetRunContext,
    operation: str,
    status: Status,
    recorded_at: str,
    domain: Mapping[str, Any],
    artifact_ref: str | None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repo": REPO,
        "surface": SURFACE,
        "operation": operation,
        "run_id": context.run_id,
        "status": status,
        "github_issue": GITHUB_ISSUE,
        "recorded_at": recorded_at,
        "domain": dict(domain),
    }
    if context.github_pr:
        record["github_pr"] = context.github_pr
    if context.provider:
        record["provider"] = context.provider
    if context.model:
        record["model"] = context.model
    if context.trace_id:
        record["trace_id"] = context.trace_id
    if context.trace_url:
        record["trace_url"] = context.trace_url
    if artifact_ref:
        record["artifact_ref"] = artifact_ref
    return record


def _extraction_status(base_status: Status, summary: IntakeFleetSummary) -> Status:
    if summary.validation_status == "error":
        return "error"
    if summary.retry_count > 0 or summary.escalation_state not in {"none", "accepted"}:
        return "fallback"
    return base_status


def _field_value(fields: Iterable[object], key: str) -> object | None:
    for field in fields:
        if getattr(field, "key", None) == key:
            return getattr(field, "value", None)
    return None


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
