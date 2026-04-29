"""V1 acceptance smoke for the local intake-to-scoring path."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from inv_man_intake.extraction.confidence import (
    ThresholdConfig,
    attach_threshold_summary,
    evaluate_thresholds,
)
from inv_man_intake.extraction.orchestrator import ExtractionOrchestrator
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.intake.integration import register_intake_bundle_file
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.observability import (
    InMemoryTraceSink,
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

_FIXTURE_ROOT = Path("tests/fixtures/intake")
_SMOKE_PACKAGE_ID = "pkg_pdf_mixed_001"
_EXPECTED_DOCUMENT_IDS = (
    "pkg_pdf_mixed_001:doc:0",
    "pkg_pdf_mixed_001:doc:1",
    "pkg_pdf_mixed_001:doc:2",
    "pkg_pdf_mixed_001:doc:3",
)


def test_v1_acceptance_smoke_exercises_intake_to_scoring_path() -> None:
    sink = InMemoryTraceSink()
    tracer = Tracer(enabled=True, sink=sink)
    trace_context = new_trace_context(tags={"package_id": _SMOKE_PACKAGE_ID, "stage": "intake"})

    service = IngestionService()
    with tracer.start_span(
        name="v1_acceptance.intake_register",
        context=trace_context,
        metadata={"fixture": "pdf_primary_mixed_bundle.json"},
    ):
        registration = register_intake_bundle_file(
            _FIXTURE_ROOT / "pdf_primary_mixed_bundle.json",
            service,
        )

    record = _assert_registered_package_state(service=service, package_id=_SMOKE_PACKAGE_ID)
    assert registration.accepted is True
    assert registration.package_id == record.package_id

    intake_start = _start_event(sink, "v1_acceptance.intake_register")
    carrier = inject_trace_context(trace_context)
    extracted_context = extract_trace_context(carrier)
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
    extraction_fields = {field.key: field for field in extraction_with_thresholds.fields}

    assert extraction_fields["strategy.asset_class"].source_doc_id in record.document_ids
    assert extraction_fields["strategy.asset_class"].source_page == 2
    assert threshold_decision.auto_pass_document is False
    assert threshold_decision.escalate is True
    assert threshold_decision.escalation_reason == "low_key_field_coverage"
    assert extraction_fields["confidence.document.escalation_reason"].value == (
        "low_key_field_coverage"
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

    assert conflict_result.escalate is True
    assert conflict_result.conflict_count == 1
    assert conflict_result.audit_entries
    assert normalized.missing_months == ()
    assert normalized.canonical_months[0].monthly_value == pytest.approx(0.021)
    assert metrics.observation_count == 6
    assert metrics.benchmark_observation_count == 6
    assert metrics.sharpe_ratio is not None
    assert metrics.benchmark_correlation is not None

    queue_assignment = create_analyst_first_assignment(
        item_id=f"{record.package_id}:validation:performance_conflict",
        analyst_id="analyst_001",
        created_at=datetime(2026, 3, 4, 10, 0, tzinfo=UTC),
    )
    assert queue_assignment.item_id == f"{record.package_id}:validation:performance_conflict"
    assert queue_assignment.owner_role == "analyst"
    assert queue_assignment.events[0].note == "analyst-first default assignment"

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

    assert score.manager_id == "fund_summit_arc_special_situations"
    assert score.final_score == pytest.approx(0.7809)
    assert formatted_explainability["overall_score"] == pytest.approx(score.final_score)
    assert formatted_explainability["components"]
    assert score.contributions["risk_adjusted_returns"] > 0

    assert {event.trace_id for event in sink.events} == {trace_context.trace_id}
    assert _start_event(sink, "extraction_orchestrator.run").parent_span_id == (
        intake_start.span_id
    )
    assert _start_event(sink, "v1_acceptance.performance_normalize").parent_span_id == (
        extraction_start.span_id
    )
    assert _start_event(sink, "v1_acceptance.scoring_compute").parent_span_id == (
        performance_start.span_id
    )


def test_v1_acceptance_smoke_fails_when_intake_registration_is_bypassed() -> None:
    service = IngestionService()
    with pytest.raises(KeyError, match="unknown package_id=pkg_pdf_mixed_001"):
        _assert_registered_package_state(service=service, package_id=_SMOKE_PACKAGE_ID)


def test_v1_acceptance_smoke_fails_when_document_identifiers_are_not_stable() -> None:
    service = IngestionService()
    register_intake_bundle_file(_FIXTURE_ROOT / "pdf_primary_mixed_bundle.json", service)

    record = service.get_record(_SMOKE_PACKAGE_ID)
    service._records[_SMOKE_PACKAGE_ID] = type(record)(
        package_id=record.package_id,
        firm_id=record.firm_id,
        fund_id=record.fund_id,
        status=record.status,
        file_count=record.file_count,
        document_ids=("volatile-doc-id",) + record.document_ids[1:],
        created_at=record.created_at,
        updated_at=record.updated_at,
        note=record.note,
    )

    with pytest.raises(AssertionError, match="document identifiers must remain stable"):
        _assert_registered_package_state(service=service, package_id=_SMOKE_PACKAGE_ID)


def test_v1_acceptance_smoke_fails_when_scoring_omits_explainability_payload() -> None:
    score = compute_score(
        ScoreSubmission(
            manager_id="fund_summit_arc_special_situations",
            asset_class="credit",
            components=_score_components(0.67),
        )
    )
    with pytest.raises(AssertionError, match="scoring output must include explainability payload"):
        _assert_score_has_explainability(score=score, explainability_payload=None)


def test_v1_acceptance_smoke_fails_when_conflict_case_lacks_queue_or_audit_evidence() -> None:
    with pytest.raises(AssertionError, match="conflict case must emit queue or audit evidence"):
        _assert_conflict_escalation_has_evidence(
            escalate=True,
            audit_entries=(),
            queue_item_id=None,
        )


def _run_extraction_smoke(
    *,
    tracer: Tracer,
    trace_context,
    source_doc_id: str,
) -> ExtractedDocumentResult:
    def primary_extractor(payload: dict[str, object]) -> dict[str, object]:
        return {
            "result": ExtractedDocumentResult(
                source_doc_id=str(payload["document_id"]),
                provider_name="fixture-primary",
                fields=(
                    ExtractedField(
                        key="strategy.asset_class",
                        value="credit",
                        confidence=0.93,
                        source_doc_id=str(payload["document_id"]),
                        source_page=2,
                    ),
                    ExtractedField(
                        key="terms.management_fee",
                        value="1.25%",
                        confidence=0.91,
                        source_doc_id=str(payload["document_id"]),
                        source_page=4,
                    ),
                    ExtractedField(
                        key="performance.net_return_1y",
                        value="8.4%",
                        confidence=0.88,
                        source_doc_id=str(payload["document_id"]),
                        source_page=8,
                    ),
                    ExtractedField(
                        key="operations.aum",
                        value="$1.2bn",
                        confidence=0.72,
                        source_doc_id=str(payload["document_id"]),
                        source_page=3,
                    ),
                    ExtractedField(
                        key="team.key_person_risk",
                        value="one senior PM departure pending",
                        confidence=0.50,
                        source_doc_id=str(payload["document_id"]),
                        source_page=11,
                    ),
                ),
            )
        }

    orchestrator = ExtractionOrchestrator(
        primary_name="fixture-primary",
        primary_extractor=primary_extractor,
        fallback_name="fixture-fallback",
        fallback_extractor=lambda payload: {"document_id": payload["document_id"]},
        tracer=tracer,
    )
    result = orchestrator.run(
        {
            "id": f"{source_doc_id}:extract",
            "document_id": source_doc_id,
        },
        trace_context=trace_context,
    )

    assert result.resolved is True
    assert result.provider_used == "fixture-primary"
    assert result.data is not None
    extracted = result.data["result"]
    assert isinstance(extracted, ExtractedDocumentResult)
    return extracted


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


def _start_event(sink: InMemoryTraceSink, name: str):
    matches = [event for event in sink.events if event.name == name and event.ended_at is None]
    assert matches, f"missing trace start event {name}"
    return matches[0]


def _assert_registered_package_state(*, service: IngestionService, package_id: str):
    record = service.get_record(package_id)
    assert record.status == "received"
    assert record.document_ids == _EXPECTED_DOCUMENT_IDS, "document identifiers must remain stable"
    assert service.get_events(package_id)[0].to_status == "received"
    return record


def _assert_score_has_explainability(
    *,
    score,
    explainability_payload: dict[str, object] | None,
) -> None:
    assert score.final_score >= 0.0
    assert explainability_payload is not None, "scoring output must include explainability payload"
    assert explainability_payload.get("components"), "scoring explainability requires components"


def _assert_conflict_escalation_has_evidence(
    *,
    escalate: bool,
    audit_entries: tuple[object, ...],
    queue_item_id: str | None,
) -> None:
    if not escalate:
        return
    assert audit_entries or queue_item_id, "conflict case must emit queue or audit evidence"
