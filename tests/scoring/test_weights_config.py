"""Tests for asset-class scoring weight configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.scoring.contracts import ScoreComponent, ScoreSubmission
from inv_man_intake.scoring.engine import compute_score, default_weights_by_asset_class
from inv_man_intake.scoring.weights import (
    ASSET_CLASS_ALIASES,
    COMPONENT_NAMES,
    LAUNCH_ASSET_CLASSES,
    get_weight_set,
    load_weight_registry,
    normalize_asset_class,
    weights_by_asset_class_for,
    weights_for_registry,
)

EXPECTED_V1_LAUNCH_ASSET_CLASSES = (
    "equity_market_neutral",
    "quant",
    "multi_strat",
    "credit_long_short",
    "macro",
    "trend_following",
    "credit_relative_value",
    "activist",
)


def _write_weight_file(
    directory: Path,
    *,
    asset_class: str,
    weights_block: str,
    version: str = "v1",
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{asset_class}.toml").write_text(
        "\n".join(
            [
                f'asset_class = "{asset_class}"',
                f'version = "{version}"',
                "",
                "[weights]",
                weights_block,
                "",
            ]
        ),
        encoding="utf-8",
    )


def _valid_weights_block() -> str:
    return "\n".join(
        [
            "performance_consistency = 0.20",
            "risk_adjusted_returns = 0.20",
            "operational_quality = 0.20",
            "transparency = 0.20",
            "team_experience = 0.20",
        ]
    )


def test_load_weight_registry_returns_all_launch_asset_classes() -> None:
    registry = load_weight_registry()

    assert set(registry) == set(LAUNCH_ASSET_CLASSES)
    for asset_class in LAUNCH_ASSET_CLASSES:
        weight_set = registry[asset_class]
        assert weight_set.asset_class == asset_class
        assert weight_set.version == "v1"
        assert set(weight_set.weights) == set(COMPONENT_NAMES)
        assert sum(weight_set.weights.values()) == pytest.approx(1.0)


def test_default_weight_fallback_matches_toml_registry() -> None:
    registry = load_weight_registry()

    assert default_weights_by_asset_class() == {
        asset_class: dict(weight_set.weights) for asset_class, weight_set in registry.items()
    }


def test_weight_registry_adapter_changes_compute_score_when_toml_changes(tmp_path: Path) -> None:
    config_dir = tmp_path / "scoring_weights"
    for asset_class in LAUNCH_ASSET_CLASSES:
        weights_block = _valid_weights_block()
        if asset_class == "credit_long_short":
            weights_block = "\n".join(
                [
                    "performance_consistency = 1.00",
                    "risk_adjusted_returns = 0.00",
                    "operational_quality = 0.00",
                    "transparency = 0.00",
                    "team_experience = 0.00",
                ]
            )
        _write_weight_file(config_dir, asset_class=asset_class, weights_block=weights_block)

    result = compute_score(
        ScoreSubmission(
            manager_id="mgr_001",
            asset_class="credit",
            components=(
                ScoreComponent("performance_consistency", 0.80),
                ScoreComponent("risk_adjusted_returns", 0.60),
                ScoreComponent("operational_quality", 0.90),
                ScoreComponent("transparency", 0.70),
                ScoreComponent("team_experience", 0.50),
            ),
        ),
        weights_by_asset_class=weights_by_asset_class_for("credit", config_dir=config_dir),
    )

    assert result.asset_class == "credit_long_short"
    assert result.final_score == pytest.approx(0.80)
    assert result.contributions["performance_consistency"] == pytest.approx(0.80)
    assert result.contributions["risk_adjusted_returns"] == pytest.approx(0.00)


def test_launch_asset_class_catalog_matches_v1_approved_classes() -> None:
    assert LAUNCH_ASSET_CLASSES == EXPECTED_V1_LAUNCH_ASSET_CLASSES

    registry = load_weight_registry()
    for asset_class in EXPECTED_V1_LAUNCH_ASSET_CLASSES:
        assert asset_class in registry


def test_get_weight_set_returns_requested_asset_class() -> None:
    weight_set = get_weight_set("equity_market_neutral")
    assert weight_set.asset_class == "equity_market_neutral"
    assert len(weight_set.ordered_weights()) == len(COMPONENT_NAMES)
    with pytest.raises(TypeError):
        weight_set.weights["performance_consistency"] = 0.9


def test_asset_class_aliases_resolve_to_launch_classes() -> None:
    assert normalize_asset_class("equity") == "equity_market_neutral"
    assert normalize_asset_class("long-short-equity") == "equity_market_neutral"
    assert normalize_asset_class("multi_strategy") == "multi_strat"
    assert normalize_asset_class("credit") == "credit_long_short"
    assert set(ASSET_CLASS_ALIASES.values()).issubset(set(LAUNCH_ASSET_CLASSES))
    assert get_weight_set("multi_asset").asset_class == "multi_strat"


def test_unknown_asset_class_rejected_with_launch_class_hint() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "unknown asset class: real_assets; expected canonical one of: .*; "
            "accepted aliases: .*"
        ),
    ):
        normalize_asset_class("real_assets")


def test_load_weight_registry_rejects_missing_launch_asset_class(tmp_path: Path) -> None:
    config_dir = tmp_path / "scoring_weights"
    for asset_class in LAUNCH_ASSET_CLASSES[:-1]:
        _write_weight_file(
            config_dir, asset_class=asset_class, weights_block=_valid_weights_block()
        )

    with pytest.raises(ValueError, match="missing launch asset class config"):
        load_weight_registry(config_dir)


def test_load_weight_registry_rejects_path_that_is_not_directory(tmp_path: Path) -> None:
    not_a_directory = tmp_path / "weights.toml"
    not_a_directory.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="is not a directory"):
        load_weight_registry(not_a_directory)


def test_load_weight_registry_rejects_missing_component_weights(tmp_path: Path) -> None:
    config_dir = tmp_path / "scoring_weights"
    weights_block = "\n".join(
        [
            "performance_consistency = 0.40",
            "risk_adjusted_returns = 0.40",
            "operational_quality = 0.20",
            "transparency = 0.00",
        ]
    )
    for asset_class in LAUNCH_ASSET_CLASSES:
        _write_weight_file(config_dir, asset_class=asset_class, weights_block=weights_block)

    with pytest.raises(ValueError, match="missing weight"):
        load_weight_registry(config_dir)


def test_load_weight_registry_rejects_sum_not_equal_to_one(tmp_path: Path) -> None:
    config_dir = tmp_path / "scoring_weights"
    bad_total = "\n".join(
        [
            "performance_consistency = 0.25",
            "risk_adjusted_returns = 0.25",
            "operational_quality = 0.25",
            "transparency = 0.25",
            "team_experience = 0.10",
        ]
    )
    for asset_class in LAUNCH_ASSET_CLASSES:
        _write_weight_file(config_dir, asset_class=asset_class, weights_block=bad_total)

    with pytest.raises(ValueError, match="weights must sum to 1.0"):
        load_weight_registry(config_dir)


def test_load_weight_registry_rejects_unknown_component_key(tmp_path: Path) -> None:
    config_dir = tmp_path / "scoring_weights"
    unknown_component = "\n".join(
        [
            "performance_consistency = 0.25",
            "risk_adjusted_returns = 0.20",
            "operational_quality = 0.20",
            "transparency = 0.15",
            "team_experience = 0.10",
            "non_core_bonus = 0.10",
        ]
    )
    for asset_class in LAUNCH_ASSET_CLASSES:
        _write_weight_file(config_dir, asset_class=asset_class, weights_block=unknown_component)

    with pytest.raises(ValueError, match="unknown weight"):
        load_weight_registry(config_dir)


def test_load_weight_registry_rejects_asset_class_filename_mismatch(tmp_path: Path) -> None:
    config_dir = tmp_path / "scoring_weights"
    for asset_class in LAUNCH_ASSET_CLASSES:
        _write_weight_file(
            config_dir, asset_class=asset_class, weights_block=_valid_weights_block()
        )
    (config_dir / "equity.toml").write_text(
        "\n".join(
            [
                'asset_class = "credit"',
                'version = "v1"',
                "",
                "[weights]",
                _valid_weights_block(),
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match filename stem"):
        load_weight_registry(config_dir)


def test_load_weight_registry_rejects_non_launch_asset_class_file(tmp_path: Path) -> None:
    config_dir = tmp_path / "scoring_weights"
    for asset_class in LAUNCH_ASSET_CLASSES:
        _write_weight_file(
            config_dir, asset_class=asset_class, weights_block=_valid_weights_block()
        )
    _write_weight_file(config_dir, asset_class="real_assets", weights_block=_valid_weights_block())

    with pytest.raises(ValueError, match="unsupported launch asset_class 'real_assets'"):
        load_weight_registry(config_dir)


_DISTINCT_COMPONENTS = (
    ScoreComponent("performance_consistency", 0.9),
    ScoreComponent("risk_adjusted_returns", 0.1),
    ScoreComponent("operational_quality", 0.5),
    ScoreComponent("transparency", 0.5),
    ScoreComponent("team_experience", 0.5),
)


def test_compute_score_works_for_all_launch_classes() -> None:
    """Every launch asset class must be scorable through the registry weights — not just credit.
    Regression for #693, where a single-class weight map made non-credit submissions raise."""
    registry_weights = weights_for_registry()
    for asset_class in LAUNCH_ASSET_CLASSES:
        submission = ScoreSubmission(
            manager_id="mgr_all",
            asset_class=asset_class,
            components=_DISTINCT_COMPONENTS,
        )
        result = compute_score(submission, weights_by_asset_class=registry_weights)
        assert 0.0 <= result.base_score <= 1.0


def test_each_class_uses_its_own_toml_weights() -> None:
    """A non-credit class scores by its OWN weight table, distinct from credit. Editing
    config/scoring_weights/macro.toml must move the macro score (deliberate-break target)."""
    registry_weights = weights_for_registry()

    def base_for(asset_class: str) -> float:
        submission = ScoreSubmission(
            manager_id="mgr",
            asset_class=asset_class,
            components=_DISTINCT_COMPONENTS,
        )
        return compute_score(submission, weights_by_asset_class=registry_weights).base_score

    # macro.toml: 0.28/0.27/0.15/0.10/0.20 → 0.9*.28+0.1*.27+0.5*(.15+.10+.20)=0.504
    assert base_for("macro") == pytest.approx(0.504)
    # credit_long_short.toml: 0.25/0.30/0.20/0.15/0.10 → 0.480 (distinct from macro)
    assert base_for("credit_long_short") == pytest.approx(0.480)
    assert base_for("macro") != base_for("credit_long_short")
