"""Contracts for deterministic scoring computations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ScoreComponent:
    """Single normalized component score in the [0, 1] range."""

    name: str
    value: float


@dataclass(frozen=True)
class ScoreSubmission:
    """Canonical scoring input for one manager and asset class."""

    manager_id: str
    asset_class: str
    components: tuple[ScoreComponent, ...]


@dataclass(frozen=True)
class RedFlagDecision:
    """Optional red-flag override decision for total score."""

    capped_score: float | None = None
    blocked: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class ScoreResult:
    """Deterministic score output with contribution breakdown."""

    manager_id: str
    asset_class: str
    base_score: float
    final_score: float
    contributions: Mapping[str, float]
    red_flag_applied: bool
    red_flag_reason: str | None


def freeze_mapping(values: dict[str, float]) -> Mapping[str, float]:
    """Return an immutable mapping for output contracts."""

    return MappingProxyType(values)
