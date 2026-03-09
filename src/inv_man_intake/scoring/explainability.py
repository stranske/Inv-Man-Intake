"""Explainability payload contract and deterministic formatter for scoring output."""

from __future__ import annotations

from dataclasses import dataclass

_ROUND_PRECISION = 6
_RECONCILIATION_TOLERANCE = 1e-6


@dataclass(frozen=True)
class ScoreComponentInput:
    """Input component used to compute contribution values."""

    component: str
    weight: float
    score: float
    rationale: str


@dataclass(frozen=True)
class ScoreComponentOutput:
    """Deterministic explainability output for one score component."""

    component: str
    weight: float
    contribution: float
    rationale: str


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

    normalized = tuple(_normalize_component(component) for component in components)
    ordered = tuple(sorted(normalized, key=lambda component: component.component))

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
            }
            for component in payload.components
        ],
    }


def _normalize_component(component: ScoreComponentInput) -> ScoreComponentOutput:
    if not component.component:
        raise ValueError("component must be non-empty")
    if not component.rationale:
        raise ValueError(f"{component.component}.rationale must be non-empty")
    if component.weight < 0:
        raise ValueError(f"{component.component}.weight must be >= 0")
    if component.score < 0 or component.score > 1:
        raise ValueError(f"{component.component}.score must be between 0 and 1")

    return ScoreComponentOutput(
        component=component.component,
        weight=_round(component.weight),
        contribution=_round(component.weight * component.score),
        rationale=component.rationale,
    )


def _round(value: float) -> float:
    return round(value, _ROUND_PRECISION)
