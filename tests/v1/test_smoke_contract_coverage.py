"""Regression guards for v1 smoke contract coverage."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.performance.metrics import PerformanceMetrics
from inv_man_intake.scoring.explainability import ComponentProvenance
from inv_man_intake.v1_smoke import (
    _evidence_backed_score_components,
    _field_component_provenance,
    _parse_aum,
    _parse_percent,
    _score_components,
    _workbook_component_provenance,
)

SMOKE_PATH = Path("src/inv_man_intake/v1_smoke.py")
AUDIT_REPORT_PATH = Path("docs/reports/v1_smoke_contract_audit.md")
PR_DESCRIPTION_PATH = Path("docs/reports/pr-403-description.md")


def _derived_extraction(**field_overrides: object) -> ExtractedDocumentResult:
    values = {
        "strategy.asset_class": "credit",
        "terms.management_fee": "1.25%",
        "performance.net_return_1y": "8.4%",
        "operations.aum": "$1.2bn",
        "team.key_person_risk": "one senior PM departure pending",
    }
    fields = []
    for key, value in values.items():
        override = field_overrides.get(key, {})
        assert isinstance(override, dict)
        fields.append(
            ExtractedField(
                key=key,
                value=override.get("value", value),  # type: ignore[arg-type]
                confidence=override.get("confidence", 0.80),  # type: ignore[arg-type]
                source_doc_id=override.get("source_doc_id", "doc-1"),  # type: ignore[arg-type]
                source_page=override.get("source_page", 2),  # type: ignore[arg-type]
                method="test",
            )
        )
    if field_overrides.get("__drop__"):
        fields = [f for f in fields if f.key != field_overrides["__drop__"]]
    return ExtractedDocumentResult(
        source_doc_id="doc-1", provider_name="test", fields=tuple(fields)
    )


def _derived_metrics(**overrides: object) -> PerformanceMetrics:
    payload: dict[str, object] = {
        "annualized_volatility": 0.10,
        "max_drawdown": 0.05,
        "sharpe_ratio": 1.0,
        "sortino_ratio": 1.4,
        "information_ratio": None,
        "benchmark_correlation": None,
        "observation_count": 12,
        "benchmark_observation_count": 0,
        "insufficient_data": (),
    }
    payload.update(overrides)
    return PerformanceMetrics(**payload)  # type: ignore[arg-type]


def _derived_scores(extraction=None, metrics=None) -> dict[str, float] | None:
    derived = _evidence_backed_score_components(
        extraction=extraction or _derived_extraction(),
        metrics=_derived_metrics() if metrics is None else metrics,
        workbook_ref="track.xlsx@doc-1",
    )
    if derived is None:
        return None
    return {component.name: component.value for component in derived.components}


def test_evidence_backed_components_are_derived_not_smoke_constants() -> None:
    scores = _derived_scores()
    assert scores is not None
    smoke = {c.name: c.value for c in _score_components(0.65)}
    # Only coincidental equality is allowed; the derived mapping must differ.
    assert scores != smoke
    assert scores["performance_consistency"] == pytest.approx(0.86)
    assert scores["risk_adjusted_returns"] == pytest.approx(0.824)
    assert scores["transparency"] == pytest.approx(0.80)
    assert scores["team_experience"] == pytest.approx(0.35)


def test_evidence_backed_transparency_tracks_mean_confidence_only() -> None:
    baseline = _derived_scores()
    lowered = _derived_scores(
        extraction=_derived_extraction(**{"operations.aum": {"confidence": 0.50}})
    )
    assert baseline is not None and lowered is not None
    assert lowered["transparency"] == pytest.approx((0.80 * 4 + 0.50) / 5)
    assert lowered["transparency"] < baseline["transparency"]
    for name in (
        "performance_consistency",
        "risk_adjusted_returns",
        "operational_quality",
        "team_experience",
    ):
        assert lowered[name] == pytest.approx(baseline[name]), name


@pytest.mark.parametrize(
    "extraction,metrics",
    [
        (_derived_extraction(__drop__="operations.aum"), _derived_metrics()),
        (_derived_extraction(**{"terms.management_fee": {"confidence": 0.49}}), _derived_metrics()),
        (_derived_extraction(**{"operations.aum": {"source_page": None}}), _derived_metrics()),
        (_derived_extraction(**{"operations.aum": {"source_doc_id": ""}}), _derived_metrics()),
        (_derived_extraction(**{"operations.aum": {"value": "  "}}), _derived_metrics()),
        (_derived_extraction(**{"strategy.asset_class": {"value": "banana"}}), _derived_metrics()),
        (_derived_extraction(**{"terms.management_fee": {"value": "n/a"}}), _derived_metrics()),
        (
            _derived_extraction(**{"performance.net_return_1y": {"value": "n/a"}}),
            _derived_metrics(),
        ),
        (_derived_extraction(**{"operations.aum": {"value": "unknown"}}), _derived_metrics()),
        (_derived_extraction(), _derived_metrics(observation_count=2)),
        (_derived_extraction(), _derived_metrics(annualized_volatility=None)),
        (_derived_extraction(), _derived_metrics(max_drawdown=None)),
        (_derived_extraction(), _derived_metrics(sharpe_ratio=None)),
    ],
    ids=[
        "missing-field",
        "low-confidence",
        "missing-page",
        "missing-doc",
        "empty-value",
        "unsupported-asset-class",
        "unparseable-fee",
        "unparseable-return",
        "unparseable-aum",
        "too-few-observations",
        "missing-volatility",
        "missing-drawdown",
        "missing-sharpe",
    ],
)
def test_evidence_backed_components_below_minimum_evidence(extraction, metrics) -> None:
    assert _derived_scores(extraction=extraction, metrics=metrics) is None


def test_evidence_backed_operational_quality_exact_value() -> None:
    scores = _derived_scores()
    assert scores is not None
    # AUM $1.2bn: (log10(1.2e9)-6)/4 = 0.7698; fee 1.25%: 1-0.0125/0.03 = 0.5833.
    # operational_quality = 0.6*0.7698 + 0.4*0.5833.
    assert scores["operational_quality"] == pytest.approx(0.695211, abs=1e-6)
    assert scores["operational_quality"] != 0.69  # smoke constant


@pytest.mark.parametrize(
    "aum_value",
    ["$1.2bn", "$1.2 billion", "$1200 million", "$1200m", "$1200000 thousand", "$1200000000"],
)
def test_evidence_backed_aum_units_scale_equivalently(aum_value: str) -> None:
    baseline = _derived_scores()
    scaled = _derived_scores(
        extraction=_derived_extraction(**{"operations.aum": {"value": aum_value}})
    )
    assert baseline is not None and scaled is not None
    assert scaled["operational_quality"] == pytest.approx(baseline["operational_quality"])
    for name in ("performance_consistency", "risk_adjusted_returns", "transparency"):
        assert scaled[name] == pytest.approx(baseline[name]), name


def test_evidence_backed_risk_adjusted_without_sortino_uses_sharpe_only() -> None:
    with_sortino = _derived_scores()
    without = _derived_scores(metrics=_derived_metrics(sortino_ratio=None))
    assert with_sortino is not None and without is not None
    # Sharpe-only: 0.8*clamp01(0.5+1.0/4) + 0.2*clamp01(0.5+0.084/0.20) = 0.784.
    assert without["risk_adjusted_returns"] == pytest.approx(0.784)
    assert without["risk_adjusted_returns"] != with_sortino["risk_adjusted_returns"]
    for name in ("performance_consistency", "operational_quality", "transparency"):
        assert without[name] == pytest.approx(with_sortino[name]), name


@pytest.mark.parametrize(
    "risk_value,expected",
    [
        ("no key person risk; stable team", 0.90),
        ("low risk", 0.90),
        ("one senior PM departure pending", 0.35),
        ("high key person risk", 0.40),
        ("moderate key person risk", 0.60),
        ("medium key person risk", 0.60),
        ("key person risk under review", 0.65),
    ],
)
def test_evidence_backed_team_experience_branches(risk_value: str, expected: float) -> None:
    baseline = _derived_scores()
    varied = _derived_scores(
        extraction=_derived_extraction(**{"team.key_person_risk": {"value": risk_value}})
    )
    assert baseline is not None and varied is not None
    assert varied["team_experience"] == pytest.approx(expected)
    for name in (
        "performance_consistency",
        "risk_adjusted_returns",
        "operational_quality",
        "transparency",
    ):
        assert varied[name] == pytest.approx(baseline[name]), name


@pytest.mark.parametrize(
    "risk_value,expected",
    [
        # Adverse signals outrank reassuring ones in the same text.
        ("stable team; one senior PM departure pending", 0.35),
        ("stable team; no pending departure", 0.90),
        ("stable team; no pending departure, but founder resigned", 0.35),
        ("low risk overall, but founder resigned", 0.35),
        ("stable team with high key person risk", 0.40),
        # Word boundaries: substrings must not misfire.
        ("nonexistent succession plan; high key person risk", 0.40),
        ("highly experienced team", 0.65),
    ],
)
def test_evidence_backed_team_experience_adverse_and_boundary_matching(
    risk_value: str, expected: float
) -> None:
    baseline = _derived_scores()
    varied = _derived_scores(
        extraction=_derived_extraction(**{"team.key_person_risk": {"value": risk_value}})
    )
    assert baseline is not None and varied is not None
    assert varied["team_experience"] == pytest.approx(expected)
    for name in (
        "performance_consistency",
        "risk_adjusted_returns",
        "operational_quality",
        "transparency",
    ):
        assert varied[name] == pytest.approx(baseline[name]), name


def test_evidence_backed_performance_consistency_tracks_volatility_only() -> None:
    baseline = _derived_scores()
    calmer = _derived_scores(metrics=_derived_metrics(annualized_volatility=0.05))
    assert baseline is not None and calmer is not None
    # 0.6*(1-0.05) + 0.4*(1-min(0.05*4,1)) = 0.57 + 0.32.
    assert calmer["performance_consistency"] == pytest.approx(0.89)
    assert calmer["performance_consistency"] > baseline["performance_consistency"]
    for name in ("risk_adjusted_returns", "operational_quality", "transparency"):
        assert calmer[name] == pytest.approx(baseline[name]), name


def test_evidence_backed_components_clamp_extreme_workbook_inputs() -> None:
    scores = _derived_scores(
        metrics=_derived_metrics(
            annualized_volatility=1.5, max_drawdown=0.50, sharpe_ratio=-2.0, sortino_ratio=-2.0
        )
    )
    assert scores is not None
    # Consistency clamps at 0: 0.6*(1-1.5) + 0.4*(1-min(0.5*4,1)) < 0.
    assert scores["performance_consistency"] == pytest.approx(0.0)
    # Risk: 0.8*clamp01(0.5-2/4) + 0.2*clamp01(0.5+0.084/0.20) = 0.184.
    assert scores["risk_adjusted_returns"] == pytest.approx(0.184)
    for name in ("operational_quality", "transparency", "team_experience"):
        baseline = _derived_scores()
        assert baseline is not None
        assert scores[name] == pytest.approx(baseline[name]), name


def test_evidence_backed_operational_quality_clamps_fee_and_aum() -> None:
    scores = _derived_scores(
        extraction=_derived_extraction(
            **{
                "operations.aum": {"value": "$1 trillion"},
                "terms.management_fee": {"value": "5%"},
            }
        )
    )
    # "trillion" is not a recognized unit, so this must stay unavailable
    # rather than guessing a scale from an unrecognized word.
    assert scores is None
    clamped = _derived_scores(
        extraction=_derived_extraction(
            **{
                "operations.aum": {"value": "$1000bn"},
                "terms.management_fee": {"value": "5%"},
            }
        )
    )
    assert clamped is not None
    # AUM score clamps at 1 (log10(1e12)); fee score clamps at 0 (5% > 3%).
    assert clamped["operational_quality"] == pytest.approx(0.6)


@pytest.mark.parametrize("aum_value", ["$1.2b", "$1200mm", "$1200000k"])
def test_evidence_backed_aum_single_letter_units_scale_equivalently(aum_value: str) -> None:
    baseline = _derived_scores()
    scaled = _derived_scores(
        extraction=_derived_extraction(**{"operations.aum": {"value": aum_value}})
    )
    assert baseline is not None and scaled is not None
    assert scaled["operational_quality"] == pytest.approx(baseline["operational_quality"])


@pytest.mark.parametrize(
    "risk_value,expected",
    [
        ("none", 0.90),
        ("senior PM leaving", 0.35),
        ("founder resigned", 0.35),
        ("two senior departures last year", 0.35),
        ("key person departed", 0.35),
        ("founder resigning next quarter", 0.35),
    ],
)
def test_evidence_backed_team_experience_remaining_tokens(risk_value: str, expected: float) -> None:
    varied = _derived_scores(
        extraction=_derived_extraction(**{"team.key_person_risk": {"value": risk_value}})
    )
    assert varied is not None
    assert varied["team_experience"] == pytest.approx(expected)


@pytest.mark.parametrize(
    "risk_value,expected",
    [
        ("No key-person risk", 0.90),
        ("no departures", 0.90),
        ("no one has left", 0.90),
        ("key person has left", 0.35),
        ("senior PM left the firm", 0.35),
        ("founder retired", 0.35),
        ("low risk, but senior PM left", 0.35),
        ("low key person risk", 0.90),
        ("Low-risk team", 0.90),
        ("minimal key person risk", 0.90),
        ("negligible key-person risk", 0.90),
        # Adverse signals still outrank the new reassuring spellings.
        ("low key person risk, but founder resigned", 0.35),
        ("minimal risk; one senior PM departure pending", 0.35),
    ],
)
def test_evidence_backed_team_experience_natural_spellings(
    risk_value: str, expected: float
) -> None:
    varied = _derived_scores(
        extraction=_derived_extraction(**{"team.key_person_risk": {"value": risk_value}})
    )
    assert varied is not None
    assert varied["team_experience"] == pytest.approx(expected)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.25%", 0.0125),
        ("1.25 percent", 0.0125),
        ("1.25 per cent", 0.0125),
        ("8.4 per cent", 0.084),
        ("1.25 pct", 0.0125),
        ("125 bps", 0.0125),
        ("125 bp", 0.0125),
        ("1,250 bps", 0.125),
        ("125 basis points", 0.0125),
        ("8.4%", 0.084),
        ("840 bps", 0.084),
        ("-4.0 percent", -0.04),
        ("1.25", None),
        ("n/a", None),
    ],
)
def test_parse_percent_accepts_spelled_and_bps_units(value: str, expected: float | None) -> None:
    assert _parse_percent(value) == (pytest.approx(expected) if expected is not None else None)


def test_evidence_backed_spelled_percentages_score_like_symbols() -> None:
    baseline = _derived_scores()
    spelled = _derived_scores(
        extraction=_derived_extraction(
            **{
                "terms.management_fee": {"value": "125 bps"},
                "performance.net_return_1y": {"value": "8.4 percent"},
            }
        )
    )
    assert baseline is not None and spelled is not None
    assert spelled == baseline


@pytest.mark.parametrize(
    "asset_class",
    [
        "credit long/short",
        "Credit Long-Short",
        "credit_long_short",
        "long/short equity",
        "Global Macro",
        "Market Neutral",
    ],
)
def test_evidence_backed_asset_class_separator_spellings(asset_class: str) -> None:
    derived = _evidence_backed_score_components(
        extraction=_derived_extraction(**{"strategy.asset_class": {"value": asset_class}}),
        metrics=_derived_metrics(),
        workbook_ref="track.xlsx@doc-1",
    )
    assert derived is not None
    assert derived.asset_class in {"credit_long_short", "equity_market_neutral", "macro"}


def test_workbook_component_provenance_uses_last_at_separator() -> None:
    provenance = _workbook_component_provenance("dir@track.xlsx@doc-1")
    assert provenance.reference == "dir@track.xlsx"
    assert provenance.source_doc_id == "doc-1"


def test_evidence_backed_minimum_evidence_boundaries_are_inclusive() -> None:
    # Exactly _MIN_WORKBOOK_OBSERVATIONS observations still scores.
    at_floor = _derived_scores(metrics=_derived_metrics(observation_count=3))
    assert at_floor is not None
    assert at_floor == _derived_scores()
    # Every key field exactly at _MIN_FIELD_CONFIDENCE still scores.
    fields = {
        key: {"confidence": 0.50}
        for key in (
            "strategy.asset_class",
            "terms.management_fee",
            "performance.net_return_1y",
            "operations.aum",
            "team.key_person_risk",
        )
    }
    at_confidence_floor = _derived_scores(extraction=_derived_extraction(**fields))
    assert at_confidence_floor is not None
    assert at_confidence_floor["transparency"] == pytest.approx(0.50)
    for name in (
        "performance_consistency",
        "risk_adjusted_returns",
        "operational_quality",
        "team_experience",
    ):
        assert at_confidence_floor[name] == pytest.approx(at_floor[name]), name


def test_evidence_backed_performance_consistency_tracks_drawdown_only() -> None:
    baseline = _derived_scores()
    deeper = _derived_scores(metrics=_derived_metrics(max_drawdown=0.20))
    assert baseline is not None and deeper is not None
    # 0.6*(1-0.10) + 0.4*(1-min(0.20*4,1)) = 0.54 + 0.08.
    assert deeper["performance_consistency"] == pytest.approx(0.62)
    assert deeper["performance_consistency"] < baseline["performance_consistency"]
    for name in ("risk_adjusted_returns", "operational_quality", "transparency", "team_experience"):
        assert deeper[name] == pytest.approx(baseline[name]), name


def test_evidence_backed_risk_adjusted_tracks_sharpe_only() -> None:
    baseline = _derived_scores()
    stronger = _derived_scores(metrics=_derived_metrics(sharpe_ratio=2.0))
    assert baseline is not None and stronger is not None
    # Sharpe-like (2.0+1.4)/2=1.7: 0.8*clamp01(0.5+1.7/4) + 0.2*clamp01(0.5+0.084/0.20).
    assert stronger["risk_adjusted_returns"] == pytest.approx(0.924)
    assert stronger["risk_adjusted_returns"] > baseline["risk_adjusted_returns"]
    for name in (
        "performance_consistency",
        "operational_quality",
        "transparency",
        "team_experience",
    ):
        assert stronger[name] == pytest.approx(baseline[name]), name


def test_evidence_backed_negative_net_return_lowers_risk_adjusted_only() -> None:
    baseline = _derived_scores()
    negative = _derived_scores(
        extraction=_derived_extraction(**{"performance.net_return_1y": {"value": "-4.0%"}})
    )
    assert baseline is not None and negative is not None
    # 0.8*clamp01(0.5+1.2/4) + 0.2*clamp01(0.5-0.04/0.20) = 0.64 + 0.06.
    assert negative["risk_adjusted_returns"] == pytest.approx(0.70)
    assert negative["risk_adjusted_returns"] < baseline["risk_adjusted_returns"]
    for name in (
        "performance_consistency",
        "operational_quality",
        "transparency",
        "team_experience",
    ):
        assert negative[name] == pytest.approx(baseline[name]), name


def test_evidence_backed_zero_aum_is_unavailable() -> None:
    extraction = _derived_extraction(**{"operations.aum": {"value": "$0"}})
    assert _derived_scores(extraction=extraction) is None


def test_evidence_backed_components_missing_metrics_is_unavailable() -> None:
    derived = _evidence_backed_score_components(
        extraction=_derived_extraction(), metrics=None, workbook_ref="track.xlsx@doc-1"
    )
    assert derived is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025: $1.2bn", 1_200_000_000),
        ("$1,200mn", 1_200_000_000),
        ("500mn", 500_000_000),
        ("$1,200 million", 1_200_000_000),
        ("450", 450),
        ("450 managed", None),
        ("$450M and $1.2bn", None),
        ("€1,5bn", None),
        ("1,2000 million", None),
        (".5bn", None),
    ],
)
def test_parse_aum_requires_one_recognized_amount_and_unit(
    value: str, expected: float | None
) -> None:
    assert _parse_aum(value) == expected


def test_workbook_component_provenance_splits_file_and_document_id() -> None:
    assert _workbook_component_provenance("track.xlsx@doc-1") == ComponentProvenance(
        source_kind="workbook", reference="track.xlsx", source_doc_id="doc-1"
    )


@pytest.mark.parametrize("workbook_ref", ["track.xlsx", "track.xlsx@"])
def test_workbook_component_provenance_without_document_id_keeps_file(workbook_ref: str) -> None:
    # Unresolved workbook refs stay workbook-kind with no document pointer,
    # so downstream provenance resolution cannot mistake them for a document.
    provenance = _workbook_component_provenance(workbook_ref)
    assert provenance.source_kind == "workbook"
    assert provenance.reference == "track.xlsx"
    assert provenance.source_doc_id is None
    assert provenance.source_page is None


def test_field_component_provenance_carries_document_and_page() -> None:
    field = ExtractedField(
        key="operations.aum",
        value="$1.2bn",
        confidence=0.80,
        source_doc_id="doc-1",
        source_page=2,
        method="test",
    )
    assert _field_component_provenance(field) == ComponentProvenance(
        source_kind="document",
        reference="operations.aum",
        source_doc_id="doc-1",
        source_page=2,
    )


def test_field_component_provenance_without_page_or_doc_is_unresolved() -> None:
    field = ExtractedField(
        key="operations.aum",
        value="$1.2bn",
        confidence=0.80,
        source_doc_id="",
        source_page=None,  # type: ignore[arg-type]
        method="test",
    )
    provenance = _field_component_provenance(field)
    assert provenance.source_doc_id is None
    assert provenance.source_page is None


def test_v1_smoke_contract_guard_accepts_current_smoke_path() -> None:
    assert smoke_contract_guard_violations(SMOKE_PATH.read_text()) == []


def test_v1_smoke_contract_guard_rejects_fixture_primary_provider() -> None:
    source = """
def run():
    return {"provider": "fixture-primary"}
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not use fixture-primary extraction providers"
    ]


def test_v1_smoke_contract_guard_rejects_dict_only_registration_shortcut() -> None:
    source = """
def run(service, path):
    return register_intake_bundle_file(path, service)
"""
    assert smoke_contract_guard_violations(source) == [
        "register_intake_bundle_file must pass core_repository and document_store"
    ]


def test_v1_smoke_contract_guard_rejects_register_intake_bundle_shortcut() -> None:
    source = """
def run(bundle, service):
    return register_intake_bundle(
        bundle,
        service,
        core_repository=object(),
    )
"""
    assert smoke_contract_guard_violations(source) == [
        "register_intake_bundle must pass core_repository and document_store"
    ]


def test_v1_smoke_contract_guard_accepts_positional_persistence_args() -> None:
    source = """
def run(bundle, service, core_repository, document_store):
    register_intake_bundle(bundle, service, core_repository, document_store)
    register_intake_bundle_file(path, service, core_repository, document_store)
"""
    assert smoke_contract_guard_violations(source) == []


def test_v1_smoke_contract_guard_accepts_mixed_persistence_args() -> None:
    source = """
def run(bundle, service, core_repository, document_store):
    register_intake_bundle(bundle, service, core_repository, document_store=document_store)
    register_intake_bundle_file(
        path,
        service,
        core_repository=core_repository,
        document_store=document_store,
    )
"""
    assert smoke_contract_guard_violations(source) == []


def test_v1_smoke_contract_guard_rejects_orphan_queue_state_module() -> None:
    source = """
from inv_man_intake.queue.state_machine import create_queue_item
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
    ]


def test_v1_smoke_contract_guard_rejects_orphan_queue_state_from_package_import() -> None:
    source = """
from inv_man_intake.queue import state_machine
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
    ]


def test_v1_smoke_contract_guard_deduplicates_repeated_violations() -> None:
    source = """
from inv_man_intake.queue.state_machine import create_queue_item
import inv_man_intake.queue.state_machine as state_machine
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
    ]


def test_v1_smoke_contract_audit_includes_row_level_trace_evidence() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    required_sections = (
        "## Verifier Disposition",
        "## Audit Scope Boundary",
        "## Contract File Inventory",
        "## Converged Follow-Up Mapping",
        "## Contract Row Matrix",
        "## Regression Gate Details",
        "## No New Follow-Up Rationale",
    )
    for section in required_sections:
        assert section in audit

    required_evidence = {
        "docs/contracts/intake_contract.md": (
            "src/inv_man_intake/v1_smoke.py:95-100",
            "tests/test_v1_acceptance_smoke.py:38-56",
        ),
        "docs/contracts/core_schema.md": (
            "src/inv_man_intake/v1_smoke.py:88",
            "tests/test_v1_acceptance_smoke.py:43-56",
        ),
        "docs/contracts/extraction_provider_contract.md": (
            "src/inv_man_intake/v1_smoke.py:244-273",
            "tests/test_v1_acceptance_smoke.py:66-70",
        ),
        "docs/contracts/extraction_thresholds.md": (
            "src/inv_man_intake/v1_smoke.py:130-156",
            "tests/test_v1_acceptance_smoke.py:70-75",
        ),
        "docs/contracts/performance_normalization.md": (
            "src/inv_man_intake/v1_smoke.py:164-178",
            "tests/test_v1_acceptance_smoke.py:78-90",
        ),
        "docs/contracts/queue_states.md": (
            "src/inv_man_intake/v1_smoke.py:186-195",
            "tests/test_v1_acceptance_smoke.py:92-100",
        ),
        "docs/contracts/queue_assignment_sla.md": (
            "src/inv_man_intake/v1_smoke.py:186-195",
            "tests/test_v1_acceptance_smoke.py:92-100",
        ),
        "docs/contracts/scoring_explainability.md": (
            "src/inv_man_intake/v1_smoke.py:202-219",
            "tests/test_v1_acceptance_smoke.py:102-109",
        ),
    }
    for contract, anchors in required_evidence.items():
        assert contract in audit
        for anchor in anchors:
            assert anchor in audit

    not_exercised_contracts = (
        "docs/contracts/core_schema_migration.md",
        "docs/contracts/provenance_history.md",
        "docs/contracts/agent-runner-output.md",
    )
    for contract in not_exercised_contracts:
        assert contract in audit
    assert "not-exercised" in audit
    assert "No issue filed from this audit" in audit


def test_v1_smoke_contract_audit_enumerates_contract_files_in_scope() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    expected_contract_files = (
        "docs/contracts/intake_contract.md",
        "docs/contracts/core_schema.md",
        "docs/contracts/extraction_provider_contract.md",
        "docs/contracts/queue_states.md",
        "docs/contracts/queue_assignment_sla.md",
        "docs/contracts/performance_normalization.md",
        "docs/contracts/scoring_explainability.md",
        "docs/contracts/extraction_thresholds.md",
        "docs/contracts/provenance_history.md",
        "docs/contracts/core_schema_migration.md",
        "docs/contracts/agent-runner-output.md",
        "docs/contracts/image_classification.md",
    )
    for contract_file in expected_contract_files:
        assert contract_file in audit


def test_v1_smoke_contract_audit_has_verifier_row_matrix_depth() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    row_tokens = (
        "intake.metadata.required_fields",
        "intake.files.roles_and_source_refs",
        "core_schema.repository_hierarchy",
        "core_schema.document_store_linkage",
        "core_schema.versioned_documents",
        "core_schema_migration.apply_rollback",
        "extraction.provider_identity",
        "extraction.canonical_result_fields",
        "extraction.secondary_fallback_route",
        "extraction_thresholds.low_key_field_coverage",
        "extraction_thresholds.document_escalation",
        "performance_normalization.input_periods",
        "performance_normalization.conflict_resolution",
        "performance_normalization.benchmark_correlation",
        "queue_states.validation_queue_state",
        "queue_states.orphan_state_machine_absence",
        "queue_assignment_sla.analyst_first_assignment",
        "queue_assignment_sla.ops_reassignment",
        "queue_assignment_sla.sla_breach_scheduling",
        "scoring_explainability.final_score",
        "scoring_explainability.driver_payload",
        "provenance_history.source_location_trace",
        "provenance_history.field_corrections",
        "agent-runner-output.workflow_call_outputs",
        "smoke_trace.continuity",
    )
    for token in row_tokens:
        assert token in audit

    assert audit.count("| `") >= len(row_tokens)
    assert audit.count("No issue filed from this audit") >= 5


def test_v1_smoke_contract_audit_uses_required_disposition_labels() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    allowed = {"end-to-end", "fixture-stand-in", "not-exercised", "orphan-only"}
    matrix_section = audit.split("## Contract Row Matrix", maxsplit=1)[1].split(
        "## Regression Gate Details",
        maxsplit=1,
    )[0]
    matrix_lines = [
        line
        for line in matrix_section.splitlines()
        if line.startswith("| `") and "Contract row" not in line and " --- " not in line
    ]
    dispositions = [line.split("|")[3].strip() for line in matrix_lines]
    assert dispositions
    assert "fixture-stand-in" in dispositions
    assert "orphan-only" in dispositions
    for disposition in dispositions:
        assert disposition in allowed


def test_v1_smoke_contract_audit_rows_trace_to_smoke_or_explicit_absence() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    matrix_section = audit.split("## Contract Row Matrix", maxsplit=1)[1].split(
        "## Regression Gate Details",
        maxsplit=1,
    )[0]
    matrix_lines = [
        line
        for line in matrix_section.splitlines()
        if line.startswith("| `") and "Contract row" not in line and " --- " not in line
    ]

    for line in matrix_lines:
        columns = [column.strip() for column in line.split("|")]
        row_token = columns[1]
        disposition = columns[3]
        evidence = columns[4]

        if disposition in {"end-to-end", "fixture-stand-in"}:
            assert (
                "src/inv_man_intake/v1_smoke.py" in evidence
            ), f"{row_token} must reference the v1 smoke call site"
            assert (
                "tests/test_v1_acceptance_smoke.py" in evidence
            ), f"{row_token} must reference the v1 acceptance assertion"
        if disposition == "orphan-only":
            assert (
                "tests/v1/test_smoke_contract_coverage.py" in evidence
            ), f"{row_token} must reference the guard assertion path"
        if disposition == "not-exercised":
            assert (
                "no call site" in evidence.lower()
                or "has no" in evidence.lower()
                or "does not" in evidence.lower()
                or " not " in evidence.lower()
                or "outside the v1 smoke claim" in evidence.lower()
            ), f"{row_token} must explain non-exercised absence"


def test_pr_description_references_audit_and_followup_issues() -> None:
    description = PR_DESCRIPTION_PATH.read_text()
    assert "docs/reports/v1_smoke_contract_audit.md" in description
    assert "#379" in description
    assert "#380" in description
    assert "#381" in description
    assert "Additional per-instance follow-up issues created by this audit: none." in description


def smoke_contract_guard_violations(source: str) -> list[str]:
    violations: list[str] = []
    if "fixture-primary" in source or "fixture_primary" in source:
        violations.append("v1 smoke must not use fixture-primary extraction providers")

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if _is_orphan_queue_module(node.module):
                violations.append(
                    "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
                )
            if node.module == "inv_man_intake.queue":
                for alias in node.names:
                    if alias.name == "state_machine":
                        violations.append(
                            "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
                        )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_orphan_queue_module(alias.name):
                    violations.append(
                        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
                    )
        if isinstance(node, ast.Call) and _call_name(node.func) in {
            "register_intake_bundle",
            "register_intake_bundle_file",
        }:
            call_name = _call_name(node.func)
            missing = _missing_persistence_args(call_name, node)
            if missing:
                violations.append(f"{call_name} must pass core_repository and document_store")

    # Keep stable order while suppressing duplicate hits from multi-import variants.
    return list(dict.fromkeys(violations))


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_orphan_queue_module(module_name: str | None) -> bool:
    return bool(module_name) and module_name.startswith("inv_man_intake.queue.state_machine")


def _missing_persistence_args(call_name: str, node: ast.Call) -> set[str]:
    keywords = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
    required_positions = {
        "register_intake_bundle": {"core_repository": 3, "document_store": 4},
        "register_intake_bundle_file": {"core_repository": 3, "document_store": 4},
    }[call_name]
    return {
        name
        for name, position in required_positions.items()
        if name not in keywords and len(node.args) < position
    }
