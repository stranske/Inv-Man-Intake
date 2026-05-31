"""Inv-Man-Intake scoring economic invariants.

These are properties that must hold for ANY valid ``ScoreSubmission``, grounded
in ``inv_man_intake/scoring/engine.py`` and ``weights.py`` -- NOT generic
placeholders:

  * score range:              0 <= base_score <= 1, 0 <= final_score <= 1
                              (every component is in [0, 1] and the weights are
                              non-negative and sum to 1.0, so the convex
                              combination lands in [0, 1]).
  * no NaN/inf:               every emitted scalar is finite.
  * required keys present:    base_score, final_score, the five per-component
                              contributions, and red_flag_applied.
  * contributions reconcile:  sum(contribution.*) == base_score (the engine
                              rounds each contribution to 6dp and sums them).
  * contribution bounds:      0 <= contribution.<c> <= weight(<c>) <= base_score-
                              admissible; each equals value*weight with value in
                              [0, 1], so 0 <= contribution <= weight.
  * red-flag monotonicity:    final_score <= base_score always (a cap takes the
                              MIN with base; a block sends it to 0; no override
                              can raise it).
  * red-flag flag agrees:     red_flag_applied == 1  iff  final_score < base_score
                              (within float tolerance); == 0 when they are equal.

The result type and assertion helper are shared
(``baseline_kit.InvariantResult`` / ``assert_invariants``).
"""

from __future__ import annotations

import math
from typing import Any

from baseline_kit import InvariantResult

from . import adapter

_EPS = 1e-9

# Default launch weight sets (mirrors engine.default_weights_by_asset_class); used
# only to derive the per-component upper bound for the contribution invariant.
_DEFAULT_WEIGHTS = {
    "equity_market_neutral": {
        "performance_consistency": 0.30,
        "risk_adjusted_returns": 0.25,
        "operational_quality": 0.15,
        "transparency": 0.15,
        "team_experience": 0.15,
    },
    "quant": {
        "performance_consistency": 0.27,
        "risk_adjusted_returns": 0.30,
        "operational_quality": 0.12,
        "transparency": 0.16,
        "team_experience": 0.15,
    },
    "multi_strat": {
        "performance_consistency": 0.27,
        "risk_adjusted_returns": 0.23,
        "operational_quality": 0.20,
        "transparency": 0.12,
        "team_experience": 0.18,
    },
    "credit_long_short": {
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
    "trend_following": {
        "performance_consistency": 0.22,
        "risk_adjusted_returns": 0.33,
        "operational_quality": 0.15,
        "transparency": 0.15,
        "team_experience": 0.15,
    },
    "credit_relative_value": {
        "performance_consistency": 0.24,
        "risk_adjusted_returns": 0.26,
        "operational_quality": 0.22,
        "transparency": 0.14,
        "team_experience": 0.14,
    },
    "activist": {
        "performance_consistency": 0.24,
        "risk_adjusted_returns": 0.21,
        "operational_quality": 0.20,
        "transparency": 0.20,
        "team_experience": 0.15,
    },
}

# Asset-class aliases the engine canonicalizes (mirrors weights.ASSET_CLASS_ALIASES)
# -- needed to resolve the weight set for invariant bounds when a scenario patch
# uses an alias.
_ALIASES = {
    "equity": "equity_market_neutral",
    "equity_l_s": "equity_market_neutral",
    "long_short_equity": "equity_market_neutral",
    "equity_long_short": "equity_market_neutral",
    "quantitative": "quant",
    "multi_strategy": "multi_strat",
    "multi_asset": "multi_strat",
    "credit": "credit_long_short",
    "credit_ls": "credit_long_short",
    "credit_l_s": "credit_long_short",
    "cta": "trend_following",
    "managed_futures": "trend_following",
    "relative_value_credit": "credit_relative_value",
    "distressed_credit": "credit_relative_value",
    "event_driven": "activist",
}


def _canonical_asset_class(label: str) -> str:
    key = str(label or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _ALIASES.get(key, key)


def check_scenario(scenario: dict[str, Any], base: dict[str, Any]) -> list[InvariantResult]:
    """Run every invariant against one scenario's scored metrics."""
    spec = adapter.apply_patch(base, scenario.get("patch"))
    metrics = adapter.run_scenario(scenario, base)
    asset_class = _canonical_asset_class(spec["asset_class"])
    weights = _DEFAULT_WEIGHTS.get(asset_class, {})

    results: list[InvariantResult] = []

    def add(name: str, ok: bool, detail: str, severity: str = "error") -> None:
        results.append(InvariantResult(name, bool(ok), severity, detail))

    # Required keys present.
    for key in adapter.METRIC_NAMES:
        add(f"key_present.{key}", key in metrics, f"missing key: {key}")

    # All emitted scalars finite (no NaN/inf).
    for key, value in metrics.items():
        add(f"finite.{key}", math.isfinite(float(value)), f"{key}={value}")

    base_score = float(metrics["base_score"])
    final_score = float(metrics["final_score"])
    red_flag_applied = int(metrics["red_flag_applied"])

    # Score range: convex combination of [0, 1] components with weights summing
    # to 1.0 -> total in [0, 1]. final_score shares the bound (cap clamps to
    # [0, 1]; block sends to 0).
    add(
        "base_score_in_unit_interval", -_EPS <= base_score <= 1.0 + _EPS, f"base_score={base_score}"
    )
    add(
        "final_score_in_unit_interval",
        -_EPS <= final_score <= 1.0 + _EPS,
        f"final_score={final_score}",
    )

    # Per-component contribution bounds and reconciliation.
    contrib_sum = 0.0
    for name in adapter.COMPONENT_NAMES:
        c = float(metrics[f"contribution.{name}"])
        contrib_sum += c
        weight = weights.get(name)
        upper = 1.0 if weight is None else weight
        add(
            f"contribution.{name}.in_bounds",
            -_EPS <= c <= upper + _EPS,
            f"contribution.{name}={c} (weight upper bound={upper})",
        )
    add(
        "contributions_reconcile_base_score",
        abs(contrib_sum - base_score) <= 1e-6,
        f"sum(contributions)={contrib_sum} base_score={base_score}",
    )

    # Red-flag monotonicity: no override can raise the score above base.
    add(
        "final_le_base",
        final_score <= base_score + _EPS,
        f"final_score={final_score} base_score={base_score}",
    )

    # red_flag_applied agrees with whether the final score moved.
    moved = final_score < base_score - _EPS
    add(
        "red_flag_applied_matches_move",
        red_flag_applied == (1 if moved else 0),
        f"red_flag_applied={red_flag_applied} moved={moved} "
        f"(base={base_score} final={final_score})",
    )

    return results
