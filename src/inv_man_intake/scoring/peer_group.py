"""Deterministic peer-group cohort storage and percentile ranks."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from inv_man_intake.scoring.weights import normalize_asset_class


@dataclass(frozen=True)
class CohortScore:
    """One prior manager score in an asset-class cohort."""

    asset_class: str
    manager_id: str
    base_score: float


class CohortStore(Protocol):
    """Minimal cohort lookup contract for peer-group percentile scoring."""

    def scores_for_asset_class(self, asset_class: str) -> tuple[float, ...]:
        """Return cohort base scores for a canonical or alias asset class."""


class InMemoryCohortStore:
    """Dependency-light cohort store keyed by canonical launch asset class."""

    def __init__(self, rows: Iterable[CohortScore] = ()) -> None:
        self._scores_by_asset_class: dict[str, dict[str, float]] = defaultdict(dict)
        for row in rows:
            self.add_score(row.asset_class, row.manager_id, row.base_score)

    def add_score(self, asset_class: str, manager_id: str, base_score: float) -> None:
        """Record one historical base score for a manager in an asset-class cohort."""

        if not manager_id:
            raise ValueError("manager_id must be non-empty")
        if not math.isfinite(base_score):
            raise ValueError("base_score must be finite")
        if base_score < 0.0 or base_score > 1.0:
            raise ValueError("base_score must be between 0 and 1")

        canonical_asset_class = normalize_asset_class(asset_class)
        self._scores_by_asset_class[canonical_asset_class][manager_id] = float(base_score)

    def scores_for_asset_class(self, asset_class: str) -> tuple[float, ...]:
        """Return cohort base scores for a canonical or alias asset class."""

        canonical_asset_class = normalize_asset_class(asset_class)
        return tuple(self._scores_by_asset_class.get(canonical_asset_class, {}).values())


def percentile_rank(score: float, asset_class: str, cohort: CohortStore) -> float:
    """Return midpoint empirical percentile rank for ``score`` within ``asset_class``.

    Ties use a midpoint rank: values below the score plus half of equal values, divided
    by cohort size. For example, 0.60 in [0.40, 0.50, 0.60, 0.70, 0.80] returns 50.0.
    """

    if not math.isfinite(score):
        raise ValueError("score must be finite")
    if score < 0.0 or score > 1.0:
        raise ValueError("score must be between 0 and 1")

    scores = cohort.scores_for_asset_class(asset_class)
    canonical_asset_class = normalize_asset_class(asset_class)
    if not scores:
        raise ValueError(f"cohort is empty for asset class: {canonical_asset_class}")

    less = sum(1 for value in scores if value < score and not math.isclose(value, score))
    equal = sum(1 for value in scores if math.isclose(value, score))
    percentile = ((less + (equal * 0.5)) / len(scores)) * 100.0
    return round(percentile, 6)
