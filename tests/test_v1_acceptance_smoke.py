"""V1 acceptance smoke for the local intake-to-scoring path."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from inv_man_intake.intake.integration import register_intake_bundle_file
from inv_man_intake.intake.service import IngestionService
from inv_man_intake.observability import InMemoryTraceSink
from inv_man_intake.queue.assignment import create_analyst_first_assignment
from inv_man_intake.scoring.contracts import ScoreSubmission
from inv_man_intake.scoring.engine import compute_score
from inv_man_intake.v1_smoke import (
    _assert_registered_package_state,
    _score_components,
    run_v1_smoke_pipeline,
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
    artifacts = run_v1_smoke_pipeline(
        fixture_root=_FIXTURE_ROOT,
        package_id=_SMOKE_PACKAGE_ID,
        expected_document_ids=_EXPECTED_DOCUMENT_IDS,
    )
    registration = artifacts.registration
    record = artifacts.record
    sink = artifacts.sink
    trace_context = artifacts.trace_context
    assert registration.accepted is True
    assert registration.package_id == record.package_id

    threshold_decision = artifacts.threshold_decision
    extraction_with_thresholds = artifacts.extraction_with_thresholds
    extraction_fields = {field.key: field for field in extraction_with_thresholds.fields}

    assert extraction_fields["strategy.asset_class"].source_doc_id in record.document_ids
    assert extraction_fields["strategy.asset_class"].source_page == 2
    assert threshold_decision.auto_pass_document is False
    assert threshold_decision.escalate is True
    assert threshold_decision.escalation_reason == "low_key_field_coverage"
    assert extraction_fields["confidence.document.escalation_reason"].value == (
        "low_key_field_coverage"
    )

    conflict_result = artifacts.conflict_result
    normalized = artifacts.normalized
    metrics = artifacts.metrics

    assert conflict_result.escalate is True
    assert conflict_result.conflict_count == 1
    assert conflict_result.audit_entries
    assert normalized.missing_months == ()
    assert normalized.canonical_months[0].monthly_value == pytest.approx(0.021)
    assert metrics.observation_count == 6
    assert metrics.benchmark_observation_count == 6
    assert metrics.sharpe_ratio is not None
    assert metrics.benchmark_correlation is not None

    queue_assignment = artifacts.queue_assignment
    assert queue_assignment.item_id == f"{record.package_id}:validation:performance_conflict"
    assert queue_assignment.owner_role == "analyst"
    assert queue_assignment.events[0].note == "analyst-first default assignment"

    score = artifacts.score
    formatted_explainability = artifacts.formatted_explainability

    assert score.manager_id == "fund_summit_arc_special_situations"
    assert score.final_score == pytest.approx(0.7809)
    assert formatted_explainability["overall_score"] == pytest.approx(score.final_score)
    assert formatted_explainability["components"]
    assert score.contributions["risk_adjusted_returns"] > 0

    assert {event.trace_id for event in sink.events} == {trace_context.trace_id}
    assert artifacts.extraction_start.parent_span_id == artifacts.intake_start.span_id
    assert artifacts.performance_start.parent_span_id == artifacts.extraction_start.span_id
    assert _start_event(sink, "v1_acceptance.scoring_compute").parent_span_id == (
        artifacts.performance_start.span_id
    )


def test_v1_acceptance_smoke_fails_when_intake_registration_is_bypassed() -> None:
    service = IngestionService()
    with pytest.raises(KeyError, match="unknown package_id=pkg_pdf_mixed_001"):
        _assert_registered_package_state(
            service=service,
            package_id=_SMOKE_PACKAGE_ID,
            expected_document_ids=_EXPECTED_DOCUMENT_IDS,
        )


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
        _assert_registered_package_state(
            service=service,
            package_id=_SMOKE_PACKAGE_ID,
            expected_document_ids=_EXPECTED_DOCUMENT_IDS,
        )


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


def _start_event(sink: InMemoryTraceSink, name: str):
    matches = [event for event in sink.events if event.name == name and event.ended_at is None]
    assert matches, f"missing trace start event {name}"
    return matches[0]


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
