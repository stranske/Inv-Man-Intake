"""Weight-sensitivity reporting for deterministic manager scoring."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from inv_man_intake.scoring.contracts import ScoreSubmission
from inv_man_intake.scoring.engine import compute_score
from inv_man_intake.scoring.weights import (
    COMPONENT_NAMES,
    normalize_asset_class,
    weights_for_registry,
)


@dataclass(frozen=True)
class WeightSensitivityRow:
    """One manager's baseline and perturbed rank/score movement."""

    manager_id: str
    baseline_score: float
    perturbed_score: float
    baseline_rank: int
    perturbed_rank: int
    rank_delta: int
    score_delta: float


@dataclass(frozen=True)
class WeightSensitivityReport:
    """Deterministic report for one asset-class weight perturbation."""

    asset_class: str
    baseline_weights: Mapping[str, float]
    perturbed_weights: Mapping[str, float]
    rows: tuple[WeightSensitivityRow, ...]


def weight_sensitivity_report(
    cohort: Sequence[ScoreSubmission],
    asset_class: str,
    perturbation: Mapping[str, float],
) -> WeightSensitivityReport:
    """Re-score a cohort under perturbed weights and report ranking deltas.

    ``perturbation`` values are additive deltas applied to the canonical registry weight set.
    The resulting positive weights are then renormalized to sum to 1. Runtime scoring weights
    are not changed.
    """

    canonical_asset_class = normalize_asset_class(asset_class)
    if not cohort:
        raise ValueError("cohort must contain at least one submission")
    if not perturbation:
        raise ValueError("perturbation must contain at least one component delta")

    registry_weights = weights_for_registry()
    baseline_weights = dict(registry_weights[canonical_asset_class])
    perturbed_weights = _perturbed_weight_set(baseline_weights, perturbation)

    selected = _select_cohort(cohort, canonical_asset_class)
    baseline_scores = {
        submission.manager_id: compute_score(
            submission, weights_by_asset_class=registry_weights
        ).final_score
        for submission in selected
    }
    perturbed_registry = dict(registry_weights)
    perturbed_registry[canonical_asset_class] = perturbed_weights
    perturbed_scores = {
        submission.manager_id: compute_score(
            submission, weights_by_asset_class=perturbed_registry
        ).final_score
        for submission in selected
    }

    baseline_ranks = _rank_scores(baseline_scores)
    perturbed_ranks = _rank_scores(perturbed_scores)
    rows = tuple(
        WeightSensitivityRow(
            manager_id=manager_id,
            baseline_score=baseline_scores[manager_id],
            perturbed_score=perturbed_scores[manager_id],
            baseline_rank=baseline_ranks[manager_id],
            perturbed_rank=perturbed_ranks[manager_id],
            rank_delta=baseline_ranks[manager_id] - perturbed_ranks[manager_id],
            score_delta=round(perturbed_scores[manager_id] - baseline_scores[manager_id], 6),
        )
        for manager_id in sorted(baseline_scores, key=lambda value: baseline_ranks[value])
    )
    return WeightSensitivityReport(
        asset_class=canonical_asset_class,
        baseline_weights=MappingProxyType(baseline_weights),
        perturbed_weights=MappingProxyType(perturbed_weights),
        rows=rows,
    )


def _select_cohort(
    cohort: Sequence[ScoreSubmission], canonical_asset_class: str
) -> tuple[ScoreSubmission, ...]:
    selected = tuple(
        submission
        for submission in cohort
        if normalize_asset_class(submission.asset_class) == canonical_asset_class
    )
    if not selected:
        raise ValueError(
            f"cohort contains no submissions for asset class {canonical_asset_class!r}"
        )

    manager_counts = Counter(submission.manager_id for submission in selected)
    duplicates = sorted(manager_id for manager_id, count in manager_counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"cohort contains duplicate manager_id(s): {', '.join(duplicates)}")
    return selected


def _perturbed_weight_set(
    baseline_weights: Mapping[str, float], perturbation: Mapping[str, float]
) -> dict[str, float]:
    unknown = sorted(set(perturbation) - set(COMPONENT_NAMES))
    if unknown:
        raise ValueError(f"unknown perturbation component(s): {', '.join(unknown)}")

    adjusted = dict(baseline_weights)
    for component, delta in perturbation.items():
        if not isinstance(delta, int | float) or not math.isfinite(delta):
            raise ValueError(f"perturbation {component} must be finite numeric")
        adjusted[component] += float(delta)
        if adjusted[component] < 0.0:
            raise ValueError(f"perturbation makes {component} negative")

    total = sum(adjusted.values())
    if total <= 0.0:
        raise ValueError("perturbed weights must have a positive total")
    return {component: round(adjusted[component] / total, 12) for component in COMPONENT_NAMES}


def _rank_scores(scores: Mapping[str, float]) -> dict[str, int]:
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return {manager_id: index + 1 for index, (manager_id, _) in enumerate(ordered)}
