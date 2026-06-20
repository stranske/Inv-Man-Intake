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
  * red-flag flag agrees:     red_flag_applied == 1 when a block applies, or
                              when a cap lowers final_score below base_score.

The result type and assertion helper are shared
(``baseline_kit.InvariantResult`` / ``assert_invariants``).
"""

from __future__ import annotations

import math
from typing import Any

from baseline_kit import InvariantResult
from inv_man_intake.scoring.engine import default_weights_by_asset_class
from inv_man_intake.scoring.weights import normalize_asset_class

from . import adapter

_EPS = 1e-9


def check_scenario(scenario: dict[str, Any], base: dict[str, Any]) -> list[InvariantResult]:
    """Run every invariant against one scenario's scored metrics."""
    spec = adapter.apply_patch(base, scenario.get("patch"))
    metrics = adapter.run_scenario(scenario, base)
    asset_class = normalize_asset_class(str(spec["asset_class"]))
    weights = default_weights_by_asset_class().get(asset_class, {})

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

    # A block decision applies even when the score was already at zero; a cap
    # applies only when it moves the final score downward.
    red_flag = spec.get("red_flag")
    moved = final_score < base_score - _EPS
    expected_applied = bool(
        red_flag
        and (
            red_flag.get("kind") == "block"
            or (red_flag.get("kind") == "cap" and moved)
        )
    )
    add(
        "red_flag_applied_matches_engine_semantics",
        red_flag_applied == (1 if expected_applied else 0),
        f"red_flag_applied={red_flag_applied} expected={expected_applied} "
        f"(base={base_score} final={final_score})",
    )

    return results
