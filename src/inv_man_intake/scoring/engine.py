"""Deterministic scoring engine and red-flag hooks."""

from __future__ import annotations

from typing import Protocol

from inv_man_intake.scoring.contracts import (
    RedFlagDecision,
    ScoreResult,
    ScoreSubmission,
    freeze_mapping,
)

_COMPONENT_ORDER: tuple[str, ...] = (
    "performance_consistency",
    "risk_adjusted_returns",
    "operational_quality",
    "transparency",
    "team_experience",
)


class RedFlagHook(Protocol):
    """Hook interface for score cap/override decisions."""

    def apply(self, submission: ScoreSubmission, *, base_score: float) -> RedFlagDecision:
        """Return cap/block decision for the submitted score."""


def default_weights_by_asset_class() -> dict[str, dict[str, float]]:
    """Default launch weight sets keyed by asset class."""

    return {
        "equity": {
            "performance_consistency": 0.30,
            "risk_adjusted_returns": 0.25,
            "operational_quality": 0.15,
            "transparency": 0.15,
            "team_experience": 0.15,
        },
        "credit": {
            "performance_consistency": 0.25,
            "risk_adjusted_returns": 0.30,
            "operational_quality": 0.20,
            "transparency": 0.15,
            "team_experience": 0.10,
        },
        "macro": {
            "performance_consistency": 0.28,
            "risk_adjusted_returns": 0.27,
            "operational_quality": 0.15,
            "transparency": 0.10,
            "team_experience": 0.20,
        },
        "multi_strategy": {
            "performance_consistency": 0.27,
            "risk_adjusted_returns": 0.23,
            "operational_quality": 0.20,
            "transparency": 0.12,
            "team_experience": 0.18,
        },
        "real_assets": {
            "performance_consistency": 0.24,
            "risk_adjusted_returns": 0.28,
            "operational_quality": 0.22,
            "transparency": 0.14,
            "team_experience": 0.12,
        },
    }


def compute_score(
    submission: ScoreSubmission,
    *,
    weights_by_asset_class: dict[str, dict[str, float]] | None = None,
    red_flag_hook: RedFlagHook | None = None,
) -> ScoreResult:
    """Compute deterministic total score with optional red-flag overrides."""

    if not submission.manager_id:
        raise ValueError("manager_id must be non-empty")
    if not submission.asset_class:
        raise ValueError("asset_class must be non-empty")
    if not submission.components:
        raise ValueError("components must be non-empty")

    weight_sets = (
        default_weights_by_asset_class()
        if weights_by_asset_class is None
        else weights_by_asset_class
    )
    try:
        asset_weights = weight_sets[submission.asset_class]
    except KeyError as exc:
        raise ValueError(f"unknown asset class: {submission.asset_class}") from exc

    _validate_weight_set(asset_weights)
    values = _normalize_components(submission)
    _validate_component_alignment(values, asset_weights)

    contributions = {
        name: round(values[name] * asset_weights[name], 6) for name in _COMPONENT_ORDER
    }
    base_score = round(sum(contributions.values()), 6)
    final_score = base_score
    red_flag_applied = False
    red_flag_reason: str | None = None

    if red_flag_hook is not None:
        decision = red_flag_hook.apply(submission, base_score=base_score)
        if decision.blocked:
            final_score = 0.0
            red_flag_applied = True
            red_flag_reason = decision.reason or "blocked"
        elif decision.capped_score is not None:
            if decision.capped_score < 0 or decision.capped_score > 1:
                raise ValueError("red flag capped_score must be between 0 and 1")
            final_score = min(base_score, round(decision.capped_score, 6))
            red_flag_applied = final_score != base_score
            red_flag_reason = decision.reason

    return ScoreResult(
        manager_id=submission.manager_id,
        asset_class=submission.asset_class,
        base_score=base_score,
        final_score=final_score,
        contributions=freeze_mapping(contributions),
        red_flag_applied=red_flag_applied,
        red_flag_reason=red_flag_reason,
    )


def _normalize_components(submission: ScoreSubmission) -> dict[str, float]:
    values: dict[str, float] = {}
    for component in submission.components:
        if not component.name:
            raise ValueError("component name must be non-empty")
        if component.name in values:
            raise ValueError(f"duplicate component: {component.name}")
        if component.value < 0 or component.value > 1:
            raise ValueError(f"component {component.name} must be between 0 and 1")
        values[component.name] = component.value
    return values


def _validate_component_alignment(components: dict[str, float], weights: dict[str, float]) -> None:
    missing = sorted(set(weights) - set(components))
    extra = sorted(set(components) - set(weights))
    if missing:
        raise ValueError(f"missing component(s): {', '.join(missing)}")
    if extra:
        raise ValueError(f"unknown component(s): {', '.join(extra)}")


def _validate_weight_set(weights: dict[str, float]) -> None:
    missing = sorted(set(_COMPONENT_ORDER) - set(weights))
    extra = sorted(set(weights) - set(_COMPONENT_ORDER))
    if missing:
        raise ValueError(f"weight set missing component(s): {', '.join(missing)}")
    if extra:
        raise ValueError(f"weight set has unknown component(s): {', '.join(extra)}")

    total = 0.0
    for name in _COMPONENT_ORDER:
        value = weights[name]
        if value < 0 or value > 1:
            raise ValueError(f"weight {name} must be between 0 and 1")
        total += value
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"weights must sum to 1.0 (got {total})")
