"""Adapter-level checks for patch DSL and flattened scoring output."""

from __future__ import annotations

from baseline_kit import load_catalog

from .adapter import COMPONENT_NAMES, apply_patch, run_scenario
from .conftest import CATALOG_PATH

_CATALOG = load_catalog(CATALOG_PATH)
_BASE = _CATALOG["base"]


def _scenario_with_patch(*steps: dict[str, object]) -> dict[str, object]:
    return {"id": "inline", "patch": list(steps)}


def test_apply_patch_supports_component_and_asset_class_ops() -> None:
    spec = apply_patch(
        _BASE,
        [
            {"op": "set_component", "name": "risk_adjusted_returns", "value": 0.8},
            {"op": "scale_component", "name": "risk_adjusted_returns", "factor": 0.5},
            {"op": "shift_all", "delta": 0.1},
            {"op": "set_asset_class", "value": "trend_following"},
        ],
    )

    assert spec["asset_class"] == "trend_following"
    assert spec["components"]["risk_adjusted_returns"] == 0.5
    assert all(0.0 <= float(spec["components"][name]) <= 1.0 for name in COMPONENT_NAMES)


def test_apply_patch_supports_red_flag_ops() -> None:
    capped = apply_patch(
        _BASE,
        [{"op": "red_flag_cap", "capped_score": 0.3, "reason": "gating-breach"}],
    )
    blocked = apply_patch(_BASE, [{"op": "red_flag_block", "reason": "compliance-block"}])

    assert capped["red_flag"] == {
        "kind": "cap",
        "capped_score": 0.3,
        "reason": "gating-breach",
    }
    assert blocked["red_flag"] == {"kind": "block", "reason": "compliance-block"}


def test_run_scenario_returns_expected_flat_keys_and_types() -> None:
    metrics = run_scenario(_scenario_with_patch(), _BASE)

    assert set(metrics) == {
        "base_score",
        "final_score",
        "red_flag_applied",
        *(f"contribution.{name}" for name in COMPONENT_NAMES),
    }
    assert isinstance(metrics["red_flag_applied"], int)
    assert all(isinstance(metrics[f"contribution.{name}"], float) for name in COMPONENT_NAMES)


def test_red_flag_cap_and_block_reduce_final_score() -> None:
    base_metrics = run_scenario(_scenario_with_patch(), _BASE)
    capped_metrics = run_scenario(
        _scenario_with_patch({"op": "red_flag_cap", "capped_score": 0.3, "reason": "cap"}),
        _BASE,
    )
    blocked_metrics = run_scenario(
        _scenario_with_patch({"op": "red_flag_block", "reason": "block"}),
        _BASE,
    )

    assert capped_metrics["base_score"] == base_metrics["base_score"]
    assert capped_metrics["final_score"] == 0.3
    assert capped_metrics["red_flag_applied"] == 1

    assert blocked_metrics["base_score"] == base_metrics["base_score"]
    assert blocked_metrics["final_score"] == 0.0
    assert blocked_metrics["red_flag_applied"] == 1
