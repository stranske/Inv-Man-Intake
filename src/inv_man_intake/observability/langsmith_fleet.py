"""Build dashboard-safe LangSmith fleet records for intake and extraction runs."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal

SCHEMA_VERSION: Final = "langsmith-fleet/v1"
REPO: Final = "stranske/Inv-Man-Intake"
SURFACE: Final = "intake-extraction"
GITHUB_ISSUE: Final = "stranske/Inv-Man-Intake#438"
ARTIFACT_NAME: Final = "langsmith-fleet.ndjson"
DEFAULT_PROJECT: Final = "inv-man-intake"
LANGSMITH_TRACE_URL_BASE: Final = "https://smith.langchain.com/r/"
ENV_LANGSMITH_KEY: Final = "LANGSMITH_API_KEY"
ENV_LANGCHAIN_PROJECT: Final = "LANGCHAIN_PROJECT"
ENV_LANGSMITH_PROJECT: Final = "LANGSMITH_PROJECT"
ENV_LANGCHAIN_TRACING_V2: Final = "LANGCHAIN_TRACING_V2"
ENV_LANGCHAIN_API_KEY: Final = "LANGCHAIN_API_KEY"
REQUIRED_TOP_LEVEL_FIELDS: Final = frozenset(
    {
        "schema_version",
        "repo",
        "surface",
        "operation",
        "run_id",
        "status",
        "github_issue",
        "recorded_at",
        "domain",
        "error_category",
    }
)
REQUIRED_DOMAIN_FIELDS: Final = frozenset(
    {
        "package_id",
        "document_id",
        "correlation_id",
        "document_count",
        "document_ids",
        "document_types",
        "redaction_status",
        "extraction_count",
        "trace_refs",
        "validation_status",
        "confidence_state",
        "escalation_state",
        "retry_count",
        "score_count",
        "review_queue_outcome",
    }
)
ALLOWED_STATUS: Final = frozenset({"success", "error", "fallback", "no_secret", "skipped"})
SENSITIVE_FIELD_TOKENS: Final = (
    "payload",
    "document_text",
    "document_content",
    "document_body",
    "raw_document",
    "raw_text",
    "extracted_value",
    "extracted_text",
    "prompt",
    "completion",
    "model_output",
    "secret",
    "api_key",
    "ssn",
    "account_number",
    "pii",
)

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
    correlation_id: str | None = None
    recorded_at: str | None = None
    github_pr: str | None = None
    latency_ms: int | None = None
    error_category: str = "none"


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
    trace_refs: tuple[str, ...] = ()
    error_category: str | None = None


def ensure_langsmith_project_defaults(
    env: MutableMapping[str, str] | None = None,
) -> bool:
    """Apply Inv-Man-Intake LangSmith defaults to ``env`` (defaults to ``os.environ``).

    Returns True when an API key is present and defaults were applied to ``env``.
    """

    target: MutableMapping[str, str] = env if env is not None else os.environ
    api_key = target.get(ENV_LANGSMITH_KEY, "").strip()
    if not api_key:
        return False
    target.setdefault(ENV_LANGCHAIN_TRACING_V2, "true")
    target.setdefault(ENV_LANGCHAIN_PROJECT, DEFAULT_PROJECT)
    target.setdefault(ENV_LANGSMITH_PROJECT, DEFAULT_PROJECT)
    target.setdefault(ENV_LANGCHAIN_API_KEY, api_key)
    return True


def derive_trace_url(trace_id: str | None) -> str | None:
    """Return a LangSmith trace URL for a non-empty trace ID."""

    if trace_id is None:
        return None
    normalized = trace_id.strip()
    if not normalized:
        return None
    return f"{LANGSMITH_TRACE_URL_BASE}{normalized}"


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
            summary_error_category=summary.error_category,
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
            summary_error_category=summary.error_category,
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
            summary_error_category=summary.error_category,
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
            summary_error_category=summary.error_category,
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
    trace_refs: Iterable[str] = (),
    document_types: Iterable[str] | None = None,
) -> IntakeFleetSummary:
    """Create dashboard-safe domain metadata from pipeline outputs.

    ``document_types`` should be supplied by the caller when known (e.g. derived
    from per-document file metadata). When not provided, an empty tuple is used
    so the dashboard reports ``unknown`` rather than a fixed placeholder.
    """

    extraction_fields = tuple(getattr(extraction, "fields", ()))
    confidence_escalation = _field_value(extraction_fields, "confidence.document.escalation")
    escalation_reason = _field_value(extraction_fields, "confidence.document.escalation_reason")
    secondary_retry_count = getattr(secondary_extraction, "retry_count", 0)
    secondary_route = getattr(secondary_extraction, "escalation_route", None)
    derived_types: tuple[str, ...] = (
        tuple(str(item) for item in document_types) if document_types is not None else ()
    )
    return IntakeFleetSummary(
        document_ids=tuple(str(item) for item in document_ids),
        document_types=derived_types,
        extraction_count=len(extraction_fields),
        validation_status=validation_status,
        redaction_status="redacted_metadata_only",
        confidence_state="escalated" if confidence_escalation is True else "accepted",
        escalation_state=str(secondary_route or escalation_reason or "none"),
        retry_count=int(secondary_retry_count or 0),
        score_count=score_count,
        review_queue_outcome=review_queue_outcome,
        artifact_refs=tuple(sorted(str(item) for item in artifact_refs if str(item).strip())),
        trace_refs=tuple(sorted(str(item) for item in trace_refs if str(item).strip())),
        error_category=str(escalation_reason) if escalation_reason else None,
    )


def write_fleet_records(path: Path, records: Iterable[Mapping[str, Any]]) -> Path:
    """Write records as deterministic NDJSON and return the artifact path.

    Records are validated against the local Workflows fleet contract subset
    before being written, so dashboard ingestion never sees malformed,
    sensitive-payload-bearing, or unsafe-artifact-reference records.
    """

    materialized = [dict(record) for record in records]
    validate_fleet_records(materialized)
    lines = [
        json.dumps(dict(record), sort_keys=True, separators=(",", ":")) for record in materialized
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def validate_fleet_records(records: Iterable[Mapping[str, Any]]) -> None:
    """Validate records against the local Workflows fleet contract subset.

    Raises ``ValueError`` when a record is missing required top-level or
    domain fields, has an invalid status, carries an unsafe artifact
    reference, or carries a sensitive-payload field name.
    """

    for index, record in enumerate(records):
        missing = sorted(REQUIRED_TOP_LEVEL_FIELDS.difference(record))
        if missing:
            raise ValueError(f"fleet record {index} missing top-level fields: {', '.join(missing)}")
        if record["schema_version"] != SCHEMA_VERSION:
            raise ValueError(
                f"fleet record {index} has invalid schema_version: "
                f"expected {SCHEMA_VERSION!r}, got {record['schema_version']!r}"
            )
        if record["repo"] != REPO:
            raise ValueError(
                f"fleet record {index} has invalid repo: expected {REPO!r}, got {record['repo']!r}"
            )
        if record["surface"] != SURFACE:
            raise ValueError(
                f"fleet record {index} has invalid surface: "
                f"expected {SURFACE!r}, got {record['surface']!r}"
            )
        if record["status"] not in ALLOWED_STATUS:
            expected = ", ".join(sorted(ALLOWED_STATUS))
            raise ValueError(
                f"fleet record {index} has invalid status: "
                f"expected one of {{{expected}}}, got {record['status']!r}"
            )
        domain = record["domain"]
        if not isinstance(domain, Mapping):
            raise ValueError(f"fleet record {index} domain must be an object")
        domain_missing = sorted(REQUIRED_DOMAIN_FIELDS.difference(domain))
        if domain_missing:
            raise ValueError(
                f"fleet record {index} missing domain fields: {', '.join(domain_missing)}"
            )
        _validate_artifact_references(index=index, record=record)
        _validate_no_sensitive_payload(index=index, record=record)


def _validate_artifact_references(*, index: int, record: Mapping[str, Any]) -> None:
    artifact_ref = record.get("artifact_ref")
    if artifact_ref is not None and not _is_safe_artifact_ref(artifact_ref):
        raise ValueError(f"fleet record {index} artifact_ref must be a safe artifact: reference")
    domain = record["domain"]
    for key in ("artifact_refs", "report_artifacts"):
        artifacts = domain.get(key)
        if artifacts is None:
            continue
        if not isinstance(artifacts, list):
            raise ValueError(f"fleet record {index} domain.{key} must be a list")
        for artifact in artifacts:
            if not _is_safe_artifact_ref(artifact):
                raise ValueError(
                    f"fleet record {index} domain.{key} must contain safe artifact: references"
                )


def _is_safe_artifact_ref(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if not value.startswith("artifact:"):
        return False
    suffix = value.removeprefix("artifact:")
    if not suffix or suffix.strip() != suffix or "\\" in suffix:
        return False
    if suffix.startswith(("/", "\\")):
        return False
    path = PurePosixPath(suffix)
    if path.is_absolute() or not path.parts:
        return False
    if path.parts[0].endswith(":"):
        return False
    return all(part not in {"", ".", ".."} for part in path.parts)


def _validate_no_sensitive_payload(*, index: int, record: Mapping[str, Any]) -> None:
    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                key_text = str(key).casefold()
                if any(token in key_text for token in SENSITIVE_FIELD_TOKENS):
                    raise ValueError(f"fleet record {index} includes sensitive field {path}.{key}")
                walk(nested, f"{path}.{key}")
            return
        if isinstance(value, list):
            for item_index, nested in enumerate(value):
                walk(nested, f"{path}[{item_index}]")

    walk(record, "record")


def _shared_domain(*, context: FleetRunContext, summary: IntakeFleetSummary) -> dict[str, Any]:
    document_id = summary.document_ids[0] if summary.document_ids else "none"
    return {
        "package_id": context.package_id,
        "document_id": document_id,
        "correlation_id": context.correlation_id or "none",
        "document_count": len(summary.document_ids),
        "document_ids": list(summary.document_ids),
        "document_types": list(summary.document_types),
        "redaction_status": summary.redaction_status,
        "trace_refs": list(summary.trace_refs),
        "validation_status": summary.validation_status,
        "extraction_count": summary.extraction_count,
        "confidence_state": summary.confidence_state,
        "escalation_state": summary.escalation_state,
        "retry_count": summary.retry_count,
        "score_count": summary.score_count,
        "review_queue_outcome": summary.review_queue_outcome,
    }


def _record(
    *,
    context: FleetRunContext,
    operation: str,
    status: Status,
    recorded_at: str,
    domain: Mapping[str, Any],
    artifact_ref: str | None,
    summary_error_category: str | None,
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
        "error_category": summary_error_category or context.error_category or "none",
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
    if context.latency_ms is not None:
        record["latency_ms"] = max(0, int(context.latency_ms))
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
