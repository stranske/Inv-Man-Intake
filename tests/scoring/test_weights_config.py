"""Tests for asset-class scoring weight configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.scoring.weights import (
    COMPONENT_NAMES,
    LAUNCH_ASSET_CLASSES,
    get_weight_set,
    load_weight_registry,
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


def test_get_weight_set_returns_requested_asset_class() -> None:
    weight_set = get_weight_set("equity")
    assert weight_set.asset_class == "equity"
    assert len(weight_set.ordered_weights()) == len(COMPONENT_NAMES)


def test_load_weight_registry_rejects_missing_launch_asset_class(tmp_path: Path) -> None:
    config_dir = tmp_path / "scoring_weights"
    for asset_class in LAUNCH_ASSET_CLASSES[:-1]:
        _write_weight_file(config_dir, asset_class=asset_class, weights_block=_valid_weights_block())

    with pytest.raises(ValueError, match="missing launch asset class config"):
        load_weight_registry(config_dir)


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
