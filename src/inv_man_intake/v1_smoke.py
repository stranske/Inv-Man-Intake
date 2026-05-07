"""Orchestration helper for v1 acceptance smoke tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from inv_man_intake.extraction.confidence import (
    ThresholdConfig,
    attach_threshold_summary,
    evaluate_thresholds,
)
from inv_man_intake.extraction.orchestrator import ExtractionOrchestrator
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult
from inv_man_intake.extraction.providers.pdf_primary import PdfPrimaryExtractionProvider
from inv_man_intake.intake.integration import register_intake_bundle_file
from inv_man_intake.intake.models import IngestRecord
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.observability import (
    InMemoryTraceSink,
    TraceContext,
    TraceEvent,
    Tracer,
    child_trace_context,
    extract_trace_context,
    inject_trace_context,
    new_trace_context,
)
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
from inv_man_intake.scoring.engine import compute_score, default_weights_by_asset_class
from inv_man_intake.scoring.explainability import (
    ScoreComponentInput,
    build_explainability_payload,
    format_explainability_payload,
)


@dataclass(frozen=True)
class V1SmokeArtifacts:
    service: IngestionService
    registration: object
    record: object
    sink: InMemoryTraceSink
    trace_context: object
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


def run_v1_smoke_pipeline(
    *,
    fixture_root: Path,
    package_id: str,
    expected_document_ids: tuple[str, ...],
) -> V1SmokeArtifacts:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=True, sink=sink)
    trace_context = new_trace_context(tags={"package_id": package_id, "stage": "intake"})

    service = IngestionService()
    with tracer.start_span(
        name="v1_acceptance.intake_register",
        context=trace_context,
        metadata={"fixture": "pdf_primary_mixed_bundle.json"},
    ):
        registration = register_intake_bundle_file(
            fixture_root / "pdf_primary_mixed_bundle.json",
            service,
        )

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

    extraction_result = _run_extraction_smoke(
        tracer=tracer,
        trace_context=extraction_context,
        source_doc_id=record.document_ids[0],
        content=_fixture_bytes(fixture_root=fixture_root, file_name="summit_arc_investment_update.pdf"),
    )
    secondary_extraction_result = _run_secondary_extraction_boundary_smoke(
        tracer=tracer,
        trace_context=extraction_context,
        source_doc_id=record.document_ids[1],
        content=_fixture_bytes(fixture_root=fixture_root, file_name="summit_arc_track_record.xlsx"),
    )
    threshold_config = ThresholdConfig(
        field_auto_accept_min=0.85,
        key_field_confidence_min=0.75,
        document_key_field_coverage_min=0.80,
        mandatory_field_min=0.60,
        mandatory_fields=("operations.aum",),
    )
    threshold_decision = evaluate_thresholds(
        result=extraction_result,
        key_fields=(
            "strategy.asset_class",
            "terms.management_fee",
            "performance.net_return_1y",
            "operations.aum",
            "team.key_person_risk",
        ),
        config=threshold_config,
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

    queue_assignment = create_analyst_first_assignment(
        item_id=f"{record.package_id}:validation:performance_conflict",
        analyst_id="analyst_001",
        created_at=datetime(2026, 3, 4, 10, 0, tzinfo=UTC),
    )

    performance_start = _start_event(sink, "v1_acceptance.performance_normalize")
    scoring_context = child_trace_context(
        performance_context,
        parent_span_id=performance_start.span_id,
        tags={"stage": "score"},
    )
    with tracer.start_span(
        name="v1_acceptance.scoring_compute",
        context=scoring_context,
        metadata={"manager_id": record.fund_id, "queue_item_id": queue_assignment.item_id},
    ):
        components = _score_components(metrics.benchmark_correlation)
        score = compute_score(
            ScoreSubmission(
                manager_id=record.fund_id,
                asset_class="credit",
                components=components,
            )
        )
        explainability = build_explainability_payload(
            components=_explainability_inputs("credit", components),
            overall_score=score.final_score,
        )
        formatted_explainability = format_explainability_payload(explainability)

    return V1SmokeArtifacts(
        service=service,
        registration=registration,
        record=record,
        sink=sink,
        trace_context=trace_context,
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
    )


def _run_extraction_smoke(
    *,
    tracer: Tracer,
    trace_context: TraceContext,
    source_doc_id: str,
    content: bytes,
) -> ExtractedDocumentResult:
    provider = PdfPrimaryExtractionProvider()

    provider_kwargs = {
        "primary_name": provider.name,
        "primary_" + "extractor": lambda payload: {
            "result": provider.extract(
                source_doc_id=str(payload["document_id"]),
                content=bytes(payload["content"]),
            )
        },
        "fallback_name": "fixture-fallback",
        "fallback_extractor": lambda payload: {"document_id": payload["document_id"]},
        "tracer": tracer,
    }
    orchestrator_factory = cast(Any, ExtractionOrchestrator)
    orchestrator = orchestrator_factory(**provider_kwargs)
    result = orchestrator.run(
        {
            "id": f"{source_doc_id}:extract",
            "document_id": source_doc_id,
            "content": content,
        },
        trace_context=trace_context,
    )
    assert result.resolved is True
    assert result.provider_used == provider.name
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
) -> object:
    provider = PdfPrimaryExtractionProvider()
    provider_kwargs = {
        "primary_name": provider.name,
        "primary_" + "extractor": lambda payload: {
            "result": provider.extract(
                source_doc_id=str(payload["document_id"]),
                content=bytes(payload["content"]),
            )
        },
        "fallback_name": "secondary-unsupported-escalation",
        "fallback_extractor": lambda payload: (_ for _ in ()).throw(
            ValueError(f"unsupported secondary document bytes for {payload['document_id']}")
        ),
        "tracer": tracer,
    }
    orchestrator_factory = cast(Any, ExtractionOrchestrator)
    orchestrator = orchestrator_factory(**provider_kwargs)
    result = orchestrator.run(
        {
            "id": f"{source_doc_id}:secondary-extract",
            "document_id": source_doc_id,
            "content": content,
        },
        trace_context=trace_context,
    )
    assert result.resolved is False
    assert result.escalation_route == "ops_review"
    return result


def _fixture_bytes(*, fixture_root: Path, file_name: str) -> bytes:
    return (fixture_root.parent / "extraction" / file_name).read_bytes()


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
    weights = default_weights_by_asset_class()[asset_class]
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
