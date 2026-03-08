"""Asset-class scoring weight configuration loader and validator."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

COMPONENT_NAMES: tuple[str, ...] = (
    "performance_consistency",
    "risk_adjusted_returns",
    "operational_quality",
    "transparency",
    "team_experience",
)
LAUNCH_ASSET_CLASSES: tuple[str, ...] = (
    "equity",
    "credit",
    "macro",
    "multi_strategy",
    "real_assets",
)
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config" / "scoring_weights"


@dataclass(frozen=True)
class ScoringWeightSet:
    """Validated weight schema for one asset class."""

    asset_class: str
    version: str
    weights: Mapping[str, float]

    def ordered_weights(self) -> tuple[float, ...]:
        """Return values in canonical component order."""
        return tuple(self.weights[name] for name in COMPONENT_NAMES)


def load_weight_registry(config_dir: Path | None = None) -> dict[str, ScoringWeightSet]:
    """Load all scoring weight files from disk and validate launch coverage."""

    root = config_dir or DEFAULT_CONFIG_DIR
    if not root.exists():
        raise ValueError(f"scoring weight directory does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"scoring weight directory is not a directory: {root}")

    registry: dict[str, ScoringWeightSet] = {}
    for path in sorted(root.glob("*.toml")):
        weight_set = load_weight_file(path)
        if weight_set.asset_class in registry:
            raise ValueError(f"duplicate asset class config: {weight_set.asset_class}")
        registry[weight_set.asset_class] = weight_set

    missing = sorted(set(LAUNCH_ASSET_CLASSES) - set(registry))
    if missing:
        raise ValueError(f"missing launch asset class config(s): {', '.join(missing)}")
    return registry


def get_weight_set(asset_class: str, config_dir: Path | None = None) -> ScoringWeightSet:
    """Return one validated weight set for the requested asset class."""

    if config_dir is None:
        registry = _load_weight_registry_cached(str(DEFAULT_CONFIG_DIR.resolve()))
    else:
        registry = load_weight_registry(config_dir)
    try:
        return registry[asset_class]
    except KeyError as exc:
        raise ValueError(f"unknown asset class: {asset_class}") from exc


@lru_cache(maxsize=1)
def _load_weight_registry_cached(config_dir: str) -> dict[str, ScoringWeightSet]:
    return load_weight_registry(Path(config_dir))


def load_weight_file(path: Path) -> ScoringWeightSet:
    """Load and validate one TOML scoring weight file."""

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    asset_class = payload.get("asset_class")
    if not isinstance(asset_class, str) or not asset_class:
        raise ValueError(f"{path.name}: 'asset_class' must be a non-empty string")
    if asset_class != path.stem:
        raise ValueError(
            f"{path.name}: 'asset_class' value '{asset_class}' does not match filename stem '{path.stem}'"
        )

    version = payload.get("version", "v1")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{path.name}: 'version' must be a non-empty string")

    raw_weights = payload.get("weights")
    if not isinstance(raw_weights, dict):
        raise ValueError(f"{path.name}: 'weights' section is required")

    normalized = _validate_and_normalize_weights(path.name, raw_weights)
    return ScoringWeightSet(
        asset_class=asset_class,
        version=version,
        weights=MappingProxyType(normalized),
    )


def _validate_and_normalize_weights(
    source_name: str, raw_weights: Mapping[str, object]
) -> dict[str, float]:
    missing = [name for name in COMPONENT_NAMES if name not in raw_weights]
    extra = [name for name in raw_weights if name not in COMPONENT_NAMES]
    if missing:
        raise ValueError(f"{source_name}: missing weight(s): {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"{source_name}: unknown weight(s): {', '.join(sorted(extra))}")

    normalized: dict[str, float] = {}
    for component in COMPONENT_NAMES:
        value = raw_weights[component]
        if not isinstance(value, int | float):
            raise ValueError(f"{source_name}: weight '{component}' must be numeric")
        number = float(value)
        if number < 0.0 or number > 1.0:
            raise ValueError(f"{source_name}: weight '{component}' must be between 0 and 1")
        normalized[component] = number

    total = sum(normalized.values())
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"{source_name}: weights must sum to 1.0 (got {total!r})")
    return normalized
