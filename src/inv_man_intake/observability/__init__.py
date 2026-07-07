"""Observability utilities for trace and metric instrumentation."""

from typing import TYPE_CHECKING

from .entrypoints import PipelineEntrypoint, audit_intake_extraction_entrypoints
from .langsmith_fleet import (
    ARTIFACT_NAME,
    DEFAULT_PROJECT,
    GITHUB_ISSUE,
    REPO,
    SCHEMA_VERSION,
    SURFACE,
    FleetRunContext,
    IntakeFleetSummary,
    build_fleet_records,
    build_summary_from_pipeline,
    derive_trace_url,
    ensure_langsmith_project_defaults,
    validate_fleet_records,
    write_fleet_records,
)
from .langsmith_sink import LangSmithTraceSink
from .logging import (
    CORRELATION_ID_KEY,
    LogContext,
    build_log_record,
    ensure_correlation_id,
    extract_correlation_id,
    inject_correlation_id,
    new_correlation_id,
)
from .metrics import (
    ESCALATION_COUNT,
    FAILURE_COUNT,
    FALLBACK_COUNT,
    LATENCY_MS,
    InMemoryMetrics,
    MetricPoint,
)
from .tracing import (
    LANGCHAIN_TRACE_ENABLED_ENV_KEY,
    LANGSMITH_API_KEY_ENV_KEY,
    LANGSMITH_PROJECT_ENV_KEY,
    LANGSMITH_TRACE_ENABLED_ENV_KEY,
    TRACE_ENABLED_ENV_KEY,
    InMemoryTraceSink,
    TraceContext,
    TraceEvent,
    Tracer,
    child_run_context,
    child_trace_context,
    extract_trace_context,
    inject_trace_context,
    new_trace_context,
    traced_run,
    traced_span,
    tracing_enabled_from_env,
)

if TYPE_CHECKING:
    from .extraction_drift import ExtractionDriftRecord


def __getattr__(name: str) -> object:
    if name in {"ExtractionDriftRecord", "score_extraction_trace_drift"}:
        from .extraction_drift import ExtractionDriftRecord, score_extraction_trace_drift

        exports = {
            "ExtractionDriftRecord": ExtractionDriftRecord,
            "score_extraction_trace_drift": score_extraction_trace_drift,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CORRELATION_ID_KEY",
    "ESCALATION_COUNT",
    "ExtractionDriftRecord",
    "FAILURE_COUNT",
    "FALLBACK_COUNT",
    "InMemoryMetrics",
    "InMemoryTraceSink",
    "ARTIFACT_NAME",
    "DEFAULT_PROJECT",
    "FleetRunContext",
    "GITHUB_ISSUE",
    "IntakeFleetSummary",
    "LANGSMITH_API_KEY_ENV_KEY",
    "LANGSMITH_PROJECT_ENV_KEY",
    "LangSmithTraceSink",
    "LANGCHAIN_TRACE_ENABLED_ENV_KEY",
    "LANGSMITH_TRACE_ENABLED_ENV_KEY",
    "LATENCY_MS",
    "LogContext",
    "MetricPoint",
    "REPO",
    "SCHEMA_VERSION",
    "SURFACE",
    "PipelineEntrypoint",
    "TRACE_ENABLED_ENV_KEY",
    "TraceContext",
    "TraceEvent",
    "Tracer",
    "build_fleet_records",
    "build_summary_from_pipeline",
    "derive_trace_url",
    "audit_intake_extraction_entrypoints",
    "build_log_record",
    "child_run_context",
    "child_trace_context",
    "ensure_correlation_id",
    "ensure_langsmith_project_defaults",
    "extract_correlation_id",
    "extract_trace_context",
    "inject_correlation_id",
    "inject_trace_context",
    "new_correlation_id",
    "new_trace_context",
    "score_extraction_trace_drift",
    "traced_run",
    "traced_span",
    "tracing_enabled_from_env",
    "validate_fleet_records",
    "write_fleet_records",
]
