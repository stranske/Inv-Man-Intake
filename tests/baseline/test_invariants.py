"""Economic invariants on the base scenario and every catalog variant."""

from __future__ import annotations

import shutil

import pytest

from baseline_kit import assert_invariants, load_catalog
from inv_man_intake.scoring import weights as scoring_weights

from . import invariants
from .conftest import CATALOG_PATH

_CATALOG = load_catalog(CATALOG_PATH)
_BASE = _CATALOG["base"]
_SCENARIOS = _CATALOG["scenarios"]


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s["id"] for s in _SCENARIOS])
def test_scenario_invariants(scenario):
    assert_invariants(
        invariants.check_scenario(scenario, _BASE),
        context=scenario["id"],
    )


def test_blocked_floor_score_matches_engine_red_flag_semantics():
    floor_blocked = {
        "id": "floor_scores_blocked",
        "patch": [
            {"op": "set_component", "name": "performance_consistency", "value": 0.0},
            {"op": "set_component", "name": "risk_adjusted_returns", "value": 0.0},
            {"op": "set_component", "name": "operational_quality", "value": 0.0},
            {"op": "set_component", "name": "transparency", "value": 0.0},
            {"op": "set_component", "name": "team_experience", "value": 0.0},
            {"op": "red_flag_block", "reason": "floor-block"},
        ],
    }

    metrics = invariants.adapter.run_scenario(floor_blocked, _BASE)

    assert metrics["base_score"] == 0.0
    assert metrics["final_score"] == 0.0
    assert metrics["red_flag_applied"] == 1
    assert (metrics["final_score"] < metrics["base_score"]) is False
    assert_invariants(
        invariants.check_scenario(floor_blocked, _BASE),
        context=floor_blocked["id"],
    )


@pytest.mark.parametrize("asset_class", ["macro", " Macro "])
def test_contribution_bounds_track_registry_weights(tmp_path, monkeypatch, asset_class):
    config_dir = tmp_path / "scoring_weights"
    shutil.copytree(scoring_weights.DEFAULT_CONFIG_DIR, config_dir)
    macro_path = config_dir / "macro.toml"
    macro_path.write_text(
        macro_path.read_text(encoding="utf-8")
        .replace("performance_consistency = 0.28", "performance_consistency = 0.08")
        .replace("risk_adjusted_returns = 0.27", "risk_adjusted_returns = 0.47"),
        encoding="utf-8",
    )
    monkeypatch.setattr(scoring_weights, "DEFAULT_CONFIG_DIR", config_dir)
    assert scoring_weights.get_weight_set(asset_class).weights["performance_consistency"] == 0.08
    scenario = {
        "id": "lowered_registry_weight",
        "patch": [
            {"op": "set_asset_class", "value": asset_class},
            {"op": "set_component", "name": "performance_consistency", "value": 1.0},
        ],
    }

    # Real scorer output satisfies the bounds from the same temporary TOML registry.
    metrics = invariants.adapter.run_scenario(scenario, _BASE)
    assert metrics["contribution.performance_consistency"] == 0.08
    assert_invariants(invariants.check_scenario(scenario, _BASE), context=scenario["id"])

    # Inject a contribution above the new bound but below the historical 0.28.
    # Keep totals consistent so the contribution bound is the only violated invariant.
    invalid_metrics = dict(metrics)
    invalid_metrics["contribution.performance_consistency"] = 0.18
    invalid_metrics["base_score"] += 0.10
    invalid_metrics["final_score"] += 0.10
    monkeypatch.setattr(invariants.adapter, "run_scenario", lambda *_: invalid_metrics)
    results = invariants.check_scenario(scenario, _BASE)
    failed = [result.name for result in results if not result.ok]
    assert failed == ["contribution.performance_consistency.in_bounds"]
