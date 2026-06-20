"""Economic invariants on the base scenario and every catalog variant."""

from __future__ import annotations

import pytest

from baseline_kit import assert_invariants, load_catalog

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
