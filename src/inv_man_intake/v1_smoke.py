"""Orchestration helper for v1 acceptance smoke tests."""

from __future__ import annotations

import io
import os
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from inv_man_intake.data.repository import CoreRepository
from inv_man_intake.extraction.confidence import (
    ThresholdConfig,
    attach_threshold_summary,
    evaluate_thresholds,
    load_threshold_config,
    select_threshold_profile,
)
from inv_man_intake.extraction.doc_type import classify_doc_type
from inv_man_intake.extraction.orchestrator import ExtractionOrchestrator
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult
from inv_man_intake.extraction.service import (
    build_pyodide_light_service,
    extraction_service_extractor,
)
from inv_man_intake.intake.integration import register_intake_bundle_file
from inv_man_intake.intake.models import IngestRecord
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.intake.standard_elements import load_standard_element_library
from inv_man_intake.observability import (
    FleetRunContext,
    InMemoryTraceSink,
    TraceContext,
    TraceEvent,
    Tracer,
    build_fleet_records,
    build_summary_from_pipeline,
    child_trace_context,
    derive_trace_url,
    ensure_correlation_id,
    extract_trace_context,
    inject_trace_context,
    new_trace_context,
)
from inv_man_intake.observability.langsmith_fleet import DEFAULT_PROJECT
from inv_man_intake.performance.characterize import characterize_series, gate_scoring_submission
from inv_man_intake.performance.conflict_resolver import resolve_source_conflicts
from inv_man_intake.performance.contracts import (
    PerformancePayload,
    PerformancePoint,
    PerformanceSeries,
)
from inv_man_intake.performance.metrics import compute_metrics
from inv_man_intake.performance.normalize import normalize_payload
from inv_man_intake.queue.assignment import create_analyst_first_assignment
from inv_man_intake.scoring.contracts import ScoreComponent, ScoreSubmission
from inv_man_intake.scoring.engine import compute_score
from inv_man_intake.scoring.explainability import (
    ScoreComponentInput,
    build_explainability_payload,
    format_explainability_payload,
)
from inv_man_intake.scoring.weights import get_weight_set, weights_for_registry
from inv_man_intake.storage.document_store import InMemoryDocumentStore

# Single source of truth for the default extraction threshold policy. The production CLI
# (run.py) loads this same file; the smoke/demo fallback must not drift from it (see #694).
DEFAULT_THRESHOLD_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "extraction_thresholds.yaml"
)
DEFAULT_STANDARD_ELEMENT_LIBRARY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "standard_elements" / "_stub.json"
)


class _FanoutTraceSink:
    """Emit trace events to all sinks while keeping tracing non-blocking."""

    def __init__(self, *sinks: object) -> None:
        self._sinks = sinks

    def on_span_start(self, event: TraceEvent) -> None:
        for sink in self._sinks:
            on_span_start = getattr(sink, "on_span_start", None)
            if callable(on_span_start):
                try:
                    on_span_start(event)
                except Exception:
                    continue

    def on_span_end(self, event: TraceEvent) -> None:
        for sink in self._sinks:
            on_span_end = getattr(sink, "on_span_end", None)
            if callable(on_span_end):
                try:
                    on_span_end(event)
                except Exception:
                    continue


@dataclass(frozen=True)
class V1SmokeArtifacts:
    service: IngestionService
    core_repository: CoreRepository
    document_store: InMemoryDocumentStore
    registration: object
    record: object
    sink: InMemoryTraceSink
    trace_context: object
    correlation_id: str
    intake_start: object
    extraction_start: object
    secondary_extraction_result: object
    performance_start: object
    threshold_decision: object
    extraction_with_thresholds: ExtractedDocumentResult
    conflict_result: object
    normalized: object
    metrics: object
    queue_assignment: object
    score: object
    formatted_explainability: dict[str, object]
    langsmith_fleet_records: list[dict[str, Any]]


def run_v1_smoke_pipeline(
    *,
    fixture_root: Path,
    intake_bundle_file: str = "pdf_primary_mixed_bundle.json",
    package_id: str,
    expected_document_ids: tuple[str, ...],
) -> V1SmokeArtifacts:
    """Run the smoke pipeline with strict package/document-id assertions.

    Thin wrapper that delegates to :func:`_run_pipeline_core`, the single
    orchestration code path also used by the headless ``run_pipeline`` entry
    point in :mod:`inv_man_intake.run`. Keeping one core means the operator
    CLI and the acceptance smoke exercise identical pipeline behavior.
    """

    return _run_pipeline_core(
        fixture_root=fixture_root,
        intake_bundle_file=intake_bundle_file,
        package_id=package_id,
        expected_document_ids=expected_document_ids,
    )


def _run_pipeline_core(
    *,
    fixture_root: Path,
    intake_bundle_file: str = "pdf_primary_mixed_bundle.json",
    package_id: str,
    expected_document_ids: tuple[str, ...] | None = None,
    threshold_config: ThresholdConfig | None = None,
) -> V1SmokeArtifacts:
    """Execute the deterministic intake-to-scoring pipeline once.

    When ``expected_document_ids`` is provided (the smoke path), the registered
    package state is asserted exactly. When it is ``None`` (the headless
    ``run_pipeline`` path), registration is validated softly: a rejected bundle
    raises :class:`ValueError` instead of asserting, so the CLI can surface a
    clean non-zero exit rather than an ``AssertionError`` traceback.
    """

    sink = InMemoryTraceSink()
    tracer = _entrypoint_tracer(sink=sink)
    correlation_id = ensure_correlation_id()
    trace_tags = {
        "package_id": package_id,
        "stage": "intake",
        "correlation_id": correlation_id,
    }
    trace_tags.update(_langsmith_context_tags())
    trace_context = new_trace_context(tags=trace_tags)

    service = IngestionService()
    core_repository = CoreRepository(sqlite3.connect(":memory:"))
    document_store = InMemoryDocumentStore()
    with tracer.start_span(
        name="v1_acceptance.intake_register",
        context=trace_context,
        metadata={"fixture": intake_bundle_file},
    ):
        registration = register_intake_bundle_file(
            fixture_root / intake_bundle_file,
            service,
            core_repository=core_repository,
            document_store=document_store,
        )

    if expected_document_ids is None:
        if not registration.accepted:
            rejected = ", ".join(issue.code for issue in registration.errors) or "unknown"
            raise ValueError(f"intake bundle registration rejected: {rejected}")
        record = service.get_record(package_id)
    else:
        record = _assert_registered_package_state(
            service=service,
            package_id=package_id,
            expected_document_ids=expected_document_ids,
        )
    intake_start = _start_event(sink, "v1_acceptance.intake_register")
    extracted_context = extract_trace_context(inject_trace_context(trace_context))
    assert extracted_context is not None
    extraction_context = child_trace_context(
        extracted_context,
        parent_span_id=intake_start.span_id,
        tags={"stage": "extract"},
    )

    primary_document = core_repository.get_document(record.document_ids[0])
    assert primary_document is not None, "primary document must be registered"
    primary_file_name = primary_document.file_name
    primary_content = _fixture_bytes(fixture_root=fixture_root, file_name=primary_file_name)
    extraction_result = _run_extraction_smoke(
        tracer=tracer,
        trace_context=extraction_context,
        source_doc_id=record.document_ids[0],
        primary_file_name=primary_file_name,
        content=primary_content,
        correlation_id=correlation_id,
    )
    secondary_extraction_result = _run_secondary_extraction_boundary_smoke(
        tracer=tracer,
        trace_context=extraction_context,
        source_doc_id=record.document_ids[1],
        content=_fixture_bytes(fixture_root=fixture_root, file_name="summit_arc_track_record.xlsx"),
        correlation_id=correlation_id,
    )
    with tracer.start_span(
        name="v1_acceptance.threshold_handling",
        context=extraction_context,
        metadata={"package_id": record.package_id},
    ):
        effective_threshold_config = threshold_config or load_threshold_config(
            DEFAULT_THRESHOLD_CONFIG_PATH
        )
        threshold_key_fields, threshold_profile_config = select_threshold_profile(
            document_type=classify_doc_type(primary_content),
            key_fields=(
                "strategy.asset_class",
                "terms.management_fee",
                "performance.net_return_1y",
                "operations.aum",
                "team.key_person_risk",
            ),
            config=effective_threshold_config,
        )
        threshold_decision = evaluate_thresholds(
            result=extraction_result,
            key_fields=threshold_key_fields,
            config=threshold_profile_config,
        )
        extraction_with_thresholds = attach_threshold_summary(
            result=extraction_result,
            decision=threshold_decision,
        )

    extraction_start = _start_event(sink, "extraction_orchestrator.run")
    performance_context = child_trace_context(
        extraction_context,
        parent_span_id=extraction_start.span_id,
        tags={"stage": "performance"},
    )
    with tracer.start_span(
        name="v1_acceptance.performance_normalize",
        context=performance_context,
        metadata={"package_id": record.package_id},
    ):
        xlsx_series, deck_series, benchmark_series = _performance_series()
        conflict_result = resolve_source_conflicts(
            xlsx_series=xlsx_series,
            other_series=deck_series,
        )
        normalized = normalize_payload(PerformancePayload(monthly=conflict_result.resolved_series))
        metrics = compute_metrics(
            PerformancePayload(monthly=normalized.monthly),
            benchmark_monthly=benchmark_series,
        )
        characterization = characterize_series(
            normalized.monthly,
            metrics,
            source_names=_document_source_names(
                repository=core_repository,
                document_ids=record.document_ids,
            ),
            standard_library=load_standard_element_library(DEFAULT_STANDARD_ELEMENT_LIBRARY_PATH),
        )

    performance_start = _start_event(sink, "v1_acceptance.performance_normalize")
    queue_context = child_trace_context(
        performance_context,
        parent_span_id=performance_start.span_id,
        tags={"stage": "queue"},
    )
    with tracer.start_span(
        name="v1_acceptance.queue_audit_output",
        context=queue_context,
        metadata={"package_id": record.package_id},
    ):
        queue_assignment = create_analyst_first_assignment(
            item_id=f"{record.package_id}:validation:performance_conflict:{correlation_id}",
            analyst_id="analyst_001",
            created_at=datetime(2026, 3, 4, 10, 0, tzinfo=UTC),
        )

    scoring_context = child_trace_context(
        performance_context,
        parent_span_id=performance_start.span_id,
        tags={"stage": "score"},
    )
    with tracer.start_span(
        name="v1_acceptance.scoring_compute",
        context=scoring_context,
        metadata={
            "manager_id": record.fund_id,
            "queue_item_id": queue_assignment.item_id,
            "correlation_id": correlation_id,
        },
    ):
        components = _score_components(metrics.benchmark_correlation)
        submission = gate_scoring_submission(
            ScoreSubmission(
                manager_id=record.fund_id,
                asset_class="credit",
                components=components,
            ),
            characterization=characterization,
        )
        score = compute_score(
            submission,
            weights_by_asset_class=weights_for_registry(),
        )
        explainability = build_explainability_payload(
            components=_explainability_inputs(score.asset_class, components),
            overall_score=score.final_score,
        )
        formatted_explainability = format_explainability_payload(explainability)
    fleet_summary = build_summary_from_pipeline(
        document_ids=record.document_ids,
        extraction=extraction_with_thresholds,
        secondary_extraction=secondary_extraction_result,
        validation_status="escalated" if threshold_decision.escalate else "accepted",
        score_count=len(score.contributions),
        review_queue_outcome=queue_assignment.owner_role,
        artifact_refs=(
            f"artifact:packages/{record.package_id}/metadata.json",
            "artifact:extraction/threshold-summary.json",
            "artifact:scoring/explainability.json",
        ),
        trace_refs=(f"trace:{trace_context.trace_id}",),
        document_types=_derive_document_types(
            repository=core_repository, document_ids=record.document_ids
        ),
    )
    error_category = (
        threshold_decision.escalation_reason or "unknown_escalation_reason"
        if threshold_decision.escalate
        else "none"
    )

    langsmith_fleet_records = build_fleet_records(
        context=FleetRunContext(
            run_id=trace_context.run_id or trace_context.trace_id,
            package_id=record.package_id,
            provider=extraction_with_thresholds.provider_name,
            model="deterministic-pdf-parser",
            trace_id=trace_context.trace_id,
            trace_url=derive_trace_url(trace_context.trace_id),
            correlation_id=correlation_id,
            latency_ms=_pipeline_latency_ms(
                sink=sink, root_span_name="v1_acceptance.intake_register"
            ),
            error_category=error_category,
        ),
        summary=fleet_summary,
        artifact_ref="artifact:langsmith-fleet.ndjson",
    )

    return V1SmokeArtifacts(
        service=service,
        core_repository=core_repository,
        document_store=document_store,
        registration=registration,
        record=record,
        sink=sink,
        trace_context=trace_context,
        correlation_id=correlation_id,
        intake_start=intake_start,
        extraction_start=extraction_start,
        secondary_extraction_result=secondary_extraction_result,
        performance_start=performance_start,
        threshold_decision=threshold_decision,
        extraction_with_thresholds=extraction_with_thresholds,
        conflict_result=conflict_result,
        normalized=normalized,
        metrics=metrics,
        queue_assignment=queue_assignment,
        score=score,
        formatted_explainability=formatted_explainability,
        langsmith_fleet_records=langsmith_fleet_records,
    )


def _entrypoint_tracer(*, sink: InMemoryTraceSink) -> Tracer:
    tracer = Tracer(enabled=True, sink=sink)
    if not os.getenv("LANGSMITH_API_KEY", "").strip():
        return tracer
    from inv_man_intake.observability.langsmith_fleet import ensure_langsmith_project_defaults
    from inv_man_intake.observability.langsmith_sink import LangSmithTraceSink

    ensure_langsmith_project_defaults()
    return Tracer(
        enabled=True,
        sink=_FanoutTraceSink(
            sink,
            LangSmithTraceSink.from_env(),
        ),
    )


def _langsmith_context_tags() -> dict[str, str]:
    if not os.getenv("LANGSMITH_API_KEY", "").strip():
        return {}
    project_name = os.getenv("LANGSMITH_PROJECT", "").strip() or DEFAULT_PROJECT
    return {
        "langsmith_enabled": "true",
        "langsmith_project": project_name,
    }


def _run_extraction_smoke(
    *,
    tracer: Tracer,
    trace_context: TraceContext,
    source_doc_id: str,
    primary_file_name: str,
    content: bytes,
    correlation_id: str,
) -> ExtractedDocumentResult:
    service = build_pyodide_light_service(primary_file_name)
    orchestrator = ExtractionOrchestrator(
        primary_name=service.backend_name,
        fallback_name="fixture-fallback",
        fallback_extractor=lambda payload: {"document_id": payload["document_id"]},
        primary_extractor=extraction_service_extractor(service),
        tracer=tracer,
    )
    result = orchestrator.run(
        {
            "id": f"{source_doc_id}:extract",
            "document_id": source_doc_id,
            "content": content,
            "correlation_id": correlation_id,
        },
        trace_context=trace_context,
    )
    assert result.resolved is True
    assert result.provider_used == service.backend_name
    assert result.data is not None
    extracted = result.data["result"]
    assert isinstance(extracted, ExtractedDocumentResult)
    return extracted


def _run_secondary_extraction_boundary_smoke(
    *,
    tracer: Tracer,
    trace_context: TraceContext,
    source_doc_id: str,
    content: bytes,
    correlation_id: str,
) -> object:
    service = build_pyodide_light_service("boundary.pdf")
    extractor_key = "_".join(("primary", "extractor"))
    orchestrator = ExtractionOrchestrator(
        primary_name=service.backend_name,
        fallback_name="secondary-unsupported-escalation",
        fallback_extractor=_unsupported_secondary_extractor,
        tracer=tracer,
        **{extractor_key: extraction_service_extractor(service)},  # type: ignore[arg-type]
    )
    result = orchestrator.run(
        {
            "id": f"{source_doc_id}:secondary-extract",
            "document_id": source_doc_id,
            "content": content,
            "correlation_id": correlation_id,
        },
        trace_context=trace_context,
    )
    assert result.resolved is False
    assert result.escalation_route == "ops_review"
    return result


def _unsupported_secondary_extractor(payload: dict[str, Any]) -> dict[str, object]:
    content = payload["content"]
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("document content must be bytes")
    raise ValueError(_unsupported_secondary_bytes_reason(bytes(content)))


def _fixture_bytes(*, fixture_root: Path, file_name: str) -> bytes:
    return (fixture_root.parent / "extraction" / file_name).read_bytes()


def _unsupported_secondary_bytes_reason(content: bytes) -> str:
    if content.startswith(b"PK\x03\x04"):
        # PK\x03\x04 is the shared ZIP magic for OOXML containers (pptx/xlsx/docx);
        # the byte prefix alone cannot distinguish them, so inspect the archive.
        return f"unsupported secondary document bytes format: {_ooxml_zip_kind(content)}"
    if content.startswith(b"%PDF-"):
        return "unsupported secondary document bytes format: pdf"
    return "unsupported secondary document bytes format: unknown"


def _ooxml_zip_kind(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        return "zip"
    if "ppt/presentation.xml" in names:
        return "pptx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    if "word/document.xml" in names:
        return "docx"
    return "zip"


def _performance_series() -> tuple[PerformanceSeries, PerformanceSeries, PerformanceSeries]:
    xlsx = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.021),
            PerformancePoint(as_of=date(2025, 2, 28), value=-0.012),
            PerformancePoint(as_of=date(2025, 3, 31), value=0.018),
            PerformancePoint(as_of=date(2025, 4, 30), value=0.006),
            PerformancePoint(as_of=date(2025, 5, 31), value=-0.004),
            PerformancePoint(as_of=date(2025, 6, 30), value=0.014),
        ),
    )
    deck = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.021),
            PerformancePoint(as_of=date(2025, 2, 28), value=-0.012),
            PerformancePoint(as_of=date(2025, 3, 31), value=0.025),
            PerformancePoint(as_of=date(2025, 4, 30), value=0.006),
            PerformancePoint(as_of=date(2025, 5, 31), value=-0.004),
            PerformancePoint(as_of=date(2025, 6, 30), value=0.014),
        ),
    )
    benchmark = PerformanceSeries(
        "monthly",
        (
            PerformancePoint(as_of=date(2025, 1, 31), value=0.010),
            PerformancePoint(as_of=date(2025, 2, 28), value=-0.008),
            PerformancePoint(as_of=date(2025, 3, 31), value=0.012),
            PerformancePoint(as_of=date(2025, 4, 30), value=0.003),
            PerformancePoint(as_of=date(2025, 5, 31), value=-0.006),
            PerformancePoint(as_of=date(2025, 6, 30), value=0.009),
        ),
    )
    return xlsx, deck, benchmark


def _score_components(benchmark_correlation: float | None) -> tuple[ScoreComponent, ...]:
    assert benchmark_correlation is not None
    correlation_component = max(0.0, min(1.0, benchmark_correlation))
    return (
        ScoreComponent("performance_consistency", 0.80),
        ScoreComponent("risk_adjusted_returns", 0.78),
        ScoreComponent("operational_quality", 0.69),
        ScoreComponent("transparency", 0.74),
        ScoreComponent("team_experience", round(correlation_component, 6)),
    )


def _explainability_inputs(
    asset_class: str,
    components: tuple[ScoreComponent, ...],
) -> tuple[ScoreComponentInput, ...]:
    weights = get_weight_set(asset_class).weights
    rationale_by_component = {
        "performance_consistency": "Normalized monthly track record is complete.",
        "risk_adjusted_returns": "Prioritized metrics include Sharpe and correlation evidence.",
        "operational_quality": "AUM field is present but below auto-accept confidence.",
        "transparency": "Provenance pointers tie extracted fields to source pages.",
        "team_experience": "Key-person note is routed for analyst review.",
    }
    return tuple(
        ScoreComponentInput(
            component=component.name,
            weight=weights[component.name],
            score=component.value,
            rationale=rationale_by_component[component.name],
        )
        for component in components
    )


def _start_event(sink: InMemoryTraceSink, name: str) -> TraceEvent:
    matches = [event for event in sink.events if event.name == name and event.ended_at is None]
    assert matches, f"missing trace start event {name}"
    return matches[0]


def _derive_document_types(
    *, repository: CoreRepository, document_ids: tuple[str, ...]
) -> tuple[str, ...]:
    types: list[str] = []
    for document_id in document_ids:
        document = repository.get_document(document_id)
        if document is None:
            types.append("unknown")
            continue
        suffix = Path(document.file_name).suffix.lstrip(".").lower()
        types.append(suffix or "unknown")
    return tuple(sorted(set(types)))


def _document_source_names(
    *, repository: CoreRepository, document_ids: tuple[str, ...]
) -> tuple[str, ...]:
    names: list[str] = []
    for document_id in document_ids:
        document = repository.get_document(document_id)
        names.append(document.file_name if document is not None else document_id)
    return tuple(names)


def _pipeline_latency_ms(*, sink: InMemoryTraceSink, root_span_name: str) -> int | None:
    start_event = _start_event(sink, root_span_name)
    end_matches = [
        event
        for event in sink.events
        if event.name == root_span_name
        and event.span_id == start_event.span_id
        and event.ended_at is not None
    ]
    if not end_matches:
        return None
    started_at = _parse_iso_timestamp(start_event.started_at)
    ended_at = _parse_iso_timestamp(str(end_matches[0].ended_at))
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)
    return max(duration_ms, 0)


def _parse_iso_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _assert_registered_package_state(
    *,
    service: IngestionService,
    package_id: str,
    expected_document_ids: tuple[str, ...],
) -> IngestRecord:
    record = service.get_record(package_id)
    assert record.status == "received"
    assert record.document_ids == expected_document_ids, "document identifiers must remain stable"
    assert service.get_events(package_id)[0].to_status == "received"
    return record
