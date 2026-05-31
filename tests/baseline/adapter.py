"""App-specific adapter for Inv-Man-Intake deterministic scoring.

This is the ONLY app-specific piece the shared ``baseline_kit`` needs: a way to
turn an input (here, a base ``ScoreSubmission`` plus a scenario *patch*) into a
flat dict of named scalar metrics. Everything else -- directional checks,
invariants, golden masters, the coverage manifest -- is generic and lives in
``baseline_kit``.

The deterministic compute surface is
``inv_man_intake.scoring.engine.compute_score`` (no DB, no network, no LLM), so
baselines here are stable.

Scenario model
--------------
The base submission lives in ``catalog.yaml`` under ``base`` (an ``asset_class``
plus the five ``components`` in [0, 1]). Each *scenario* is the base submission
with an optional ``patch`` applied. A patch is an ordered list of operations --
the small DSL ``apply_patch`` understands:

* ``{op: set_component, name: X, value: V}`` -- overwrite one component score.
* ``{op: scale_component, name: X, factor: F}`` -- multiply one component score
  (clamped to [0, 1] so the submission stays valid).
* ``{op: shift_all, delta: D}`` -- add ``D`` to every component (clamped to
  [0, 1]); a uniform "all sleeves better/worse" move.
* ``{op: set_asset_class, value: AC}`` -- re-weight under a different asset
  class (changes which components matter most).
* ``{op: red_flag_cap, capped_score: C, reason: R}`` -- attach a red-flag hook
  that caps the final score at ``C``.
* ``{op: red_flag_block, reason: R}`` -- attach a red-flag hook that blocks
  (final score -> 0.0).

This keeps the catalog declarative and the variants directionally predictable
(raise every sleeve -> higher score; cap/block -> lower final score).

Metric flattening
-----------------
``compute_score`` returns one ``ScoreResult`` per submission. We flatten it to a
single flat ``dict[str, float | int]``:

* ``base_score``                      -- weighted total before red-flag override
* ``final_score``                     -- total after any cap/block
* ``contribution.<component>`` (x5)   -- per-component weighted contribution
* ``red_flag_applied``                -- 1 if a cap/block changed the score else 0

which is exactly what ``baseline_kit`` golden/directional/coverage machinery
consumes.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Canonical component order (mirrors engine._COMPONENT_ORDER / weights.COMPONENT_NAMES).
COMPONENT_NAMES = (
    "performance_consistency",
    "risk_adjusted_returns",
    "operational_quality",
    "transparency",
    "team_experience",
)

# Flat metric keys this surface produces (the kit's coverage "parameter" space).
METRIC_NAMES = (
    "base_score",
    "final_score",
    *(f"contribution.{name}" for name in COMPONENT_NAMES),
    "red_flag_applied",
)


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------------------
# Patch DSL
# ---------------------------------------------------------------------------


def apply_patch(base: dict[str, Any], patch: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Return a deep copy of the base submission spec with ``patch`` applied.

    The returned spec is a plain dict with keys ``asset_class``,
    ``components`` (a ``dict[name -> value]``), and optionally ``red_flag``
    (one of ``{"kind": "cap", "capped_score": C, "reason": R}`` or
    ``{"kind": "block", "reason": R}``).
    """
    spec = copy.deepcopy(base)
    spec.setdefault("components", {})
    spec.pop("red_flag", None)

    for step in patch or []:
        op = step["op"]
        if op == "set_component":
            spec["components"][step["name"]] = _clamp_unit(float(step["value"]))
        elif op == "scale_component":
            current = float(spec["components"][step["name"]])
            spec["components"][step["name"]] = _clamp_unit(current * float(step["factor"]))
        elif op == "shift_all":
            delta = float(step["delta"])
            for name in spec["components"]:
                spec["components"][name] = _clamp_unit(float(spec["components"][name]) + delta)
        elif op == "set_asset_class":
            spec["asset_class"] = str(step["value"])
        elif op == "red_flag_cap":
            spec["red_flag"] = {
                "kind": "cap",
                "capped_score": float(step["capped_score"]),
                "reason": str(step.get("reason", "cap")),
            }
        elif op == "red_flag_block":
            spec["red_flag"] = {"kind": "block", "reason": str(step.get("reason", "block"))}
        else:  # pragma: no cover - guards against catalog typos
            raise ValueError(f"unknown patch op: {op!r}")
    return spec


# ---------------------------------------------------------------------------
# Compute + flatten
# ---------------------------------------------------------------------------


def _build_red_flag_hook(spec: dict[str, Any]) -> Any:
    rf = spec.get("red_flag")
    if rf is None:
        return None

    from inv_man_intake.scoring.contracts import RedFlagDecision

    kind = rf["kind"]
    if kind == "cap":
        capped = float(rf["capped_score"])
        reason = str(rf.get("reason", "cap"))

        class _CapHook:
            def apply(self, submission: Any, *, base_score: float) -> Any:
                del submission, base_score
                return RedFlagDecision(capped_score=capped, reason=reason)

        return _CapHook()

    if kind == "block":
        reason = str(rf.get("reason", "block"))

        class _BlockHook:
            def apply(self, submission: Any, *, base_score: float) -> Any:
                del submission, base_score
                return RedFlagDecision(blocked=True, reason=reason)

        return _BlockHook()

    raise ValueError(f"unknown red_flag kind: {kind!r}")  # pragma: no cover


def run_scenario(scenario: dict[str, Any], base: dict[str, Any]) -> dict[str, float | int]:
    """Apply a scenario's patch to the base submission, score it, flatten.

    Returns a flat ``dict`` of named scalars (see module docstring). Deterministic:
    ``compute_score`` is a pure weighted sum with deterministic rounding, so the
    flattened dict is stable.
    """
    from inv_man_intake.scoring.contracts import ScoreComponent, ScoreSubmission
    from inv_man_intake.scoring.engine import compute_score

    spec = apply_patch(base, scenario.get("patch"))
    submission = ScoreSubmission(
        manager_id=str(spec.get("manager_id", "mgr_baseline")),
        asset_class=str(spec["asset_class"]),
        components=tuple(
            ScoreComponent(name, float(spec["components"][name])) for name in COMPONENT_NAMES
        ),
    )
    result = compute_score(submission, red_flag_hook=_build_red_flag_hook(spec))

    flat: dict[str, float | int] = {
        "base_score": float(result.base_score),
        "final_score": float(result.final_score),
        "red_flag_applied": int(bool(result.red_flag_applied)),
    }
    for name in COMPONENT_NAMES:
        flat[f"contribution.{name}"] = float(result.contributions[name])
    return flat


def metric_names() -> list[str]:
    return list(METRIC_NAMES)
