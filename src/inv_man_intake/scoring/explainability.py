"""Explainability payload contract and deterministic formatter for scoring output."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from inv_man_intake.scoring.engine import _COMPONENT_ORDER

_ROUND_PRECISION = 6
_RECONCILIATION_TOLERANCE = 1e-6
_COMPONENT_ORDER_INDEX = {component: index for index, component in enumerate(_COMPONENT_ORDER)}


@dataclass(frozen=True)
class ComponentProvenance:
    """Resolvable provenance pointer for one score component.

    ``source_kind`` is ``document`` (extracted field on a document page),
    ``workbook`` (submitted workbook metrics), or ``analyst`` (analyst /
    fixture-supplied judgement). ``reference`` names the field key, workbook
    file, or analyst id so callers can resolve the pointer against the run's
    per-field evidence.
    """

    source_kind: str
    reference: str
    source_doc_id: str | None = None
    source_page: int | None = None


@dataclass(frozen=True)
class ScoreComponentInput:
    """Input component used to compute contribution values."""

    component: str
    weight: float
    score: float
    rationale: str
    provenance: tuple[ComponentProvenance, ...] = ()


@dataclass(frozen=True)
class ScoreComponentOutput:
    """Deterministic explainability output for one score component."""

    component: str
    weight: float
    contribution: float
    rationale: str
    provenance: tuple[ComponentProvenance, ...] = ()


@dataclass(frozen=True)
class ExplainabilityPayload:
    """Top-level explainability contract attached to score outputs."""

    overall_score: float
    total_contribution: float
    components: tuple[ScoreComponentOutput, ...]


def build_explainability_payload(
    *,
    components: tuple[ScoreComponentInput, ...],
    overall_score: float | None = None,
) -> ExplainabilityPayload:
    """Build a deterministic explainability payload with reconciled totals."""

    if not components:
        raise ValueError("components must contain at least one component")
    if overall_score is not None and not isfinite(overall_score):
        raise ValueError("overall_score must be finite")

    normalized = tuple(_normalize_component(component) for component in components)
    component_ids = [component.component for component in normalized]
    if len(component_ids) != len(set(component_ids)):
        raise ValueError("component identifiers must be unique")
    ordered = tuple(sorted(normalized, key=_component_order_key))

    computed_total = _round(sum(component.contribution for component in ordered))
    resolved_overall = computed_total if overall_score is None else _round(overall_score)
    if abs(resolved_overall - computed_total) > _RECONCILIATION_TOLERANCE:
        raise ValueError(
            "overall_score does not reconcile with summed component contributions: "
            f"{resolved_overall} vs {computed_total}"
        )

    return ExplainabilityPayload(
        overall_score=resolved_overall,
        total_contribution=computed_total,
        components=ordered,
    )


def format_explainability_payload(payload: ExplainabilityPayload) -> dict[str, object]:
    """Format payload as a stable dictionary for API output and audit logs."""

    return {
        "overall_score": payload.overall_score,
        "total_contribution": payload.total_contribution,
        "components": [
            {
                "component": component.component,
                "weight": component.weight,
                "contribution": component.contribution,
                "rationale": component.rationale,
                "provenance": [
                    {
                        "source_kind": provenance.source_kind,
                        "reference": provenance.reference,
                        "source_doc_id": provenance.source_doc_id,
                        "source_page": provenance.source_page,
                    }
                    for provenance in component.provenance
                ],
            }
            for component in payload.components
        ],
    }


def _normalize_component(component: ScoreComponentInput) -> ScoreComponentOutput:
    component_id = component.component.strip()
    if not component_id:
        raise ValueError("component must be non-empty")
    rationale = component.rationale.strip()
    if not rationale:
        raise ValueError(f"{component_id}.rationale must be non-empty")
    if not isfinite(component.weight):
        raise ValueError(f"{component_id}.weight must be finite")
    if component.weight < 0:
        raise ValueError(f"{component_id}.weight must be >= 0")
    if not isfinite(component.score):
        raise ValueError(f"{component_id}.score must be finite")
    if component.score < 0 or component.score > 1:
        raise ValueError(f"{component_id}.score must be between 0 and 1")

    return ScoreComponentOutput(
        component=component_id,
        weight=_round(component.weight),
        contribution=_round(component.weight * component.score),
        rationale=rationale,
        provenance=tuple(
            _normalize_provenance(component_id, provenance) for provenance in component.provenance
        ),
    )


_PROVENANCE_SOURCE_KINDS = frozenset({"document", "workbook", "analyst"})


def _normalize_provenance(
    component_id: str, provenance: ComponentProvenance
) -> ComponentProvenance:
    source_kind = provenance.source_kind.strip()
    if source_kind not in _PROVENANCE_SOURCE_KINDS:
        raise ValueError(
            f"{component_id}.provenance.source_kind must be one of " "document, workbook, analyst"
        )
    reference = provenance.reference.strip()
    if not reference:
        raise ValueError(f"{component_id}.provenance.reference must be non-empty")
    source_doc_id = provenance.source_doc_id.strip() if provenance.source_doc_id else None
    if source_kind == "document":
        if not source_doc_id:
            raise ValueError(f"{component_id}.provenance.source_doc_id is required for document")
        if provenance.source_page is None or provenance.source_page < 1:
            raise ValueError(f"{component_id}.provenance.source_page must be >= 1")
    elif provenance.source_page is not None:
        raise ValueError(f"{component_id}.provenance.source_page must be null for {source_kind}")
    return ComponentProvenance(
        source_kind=source_kind,
        reference=reference,
        source_doc_id=source_doc_id,
        source_page=provenance.source_page if source_kind == "document" else None,
    )


def _component_order_key(component: ScoreComponentOutput) -> tuple[int, str]:
    return (
        _COMPONENT_ORDER_INDEX.get(component.component, len(_COMPONENT_ORDER_INDEX)),
        component.component,
    )


def _round(value: float) -> float:
    return round(value, _ROUND_PRECISION)
