"""Scoring regression and calibration primitives."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class ScoreEntry:
    """Single scoring output used for regression and calibration checks."""

    manager_id: str
    asset_class: str
    score: float


@dataclass(frozen=True)
class DriftAlert:
    """Alert raised when drift exceeds configured thresholds."""

    manager_id: str
    asset_class: str
    score_delta: float
    rank_movement: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DriftReport:
    """Deterministic drift report for baseline vs candidate scores."""

    alerts: tuple[DriftAlert, ...]
    checked_count: int
    max_score_delta_threshold: float
    max_rank_movement_threshold: int


@dataclass(frozen=True)
class CalibrationStats:
    """Per-asset-class distribution summary used in release calibration checks."""

    asset_class: str
    count: int
    mean: float
    stddev: float
    minimum: float
    p50: float
    p90: float
    maximum: float


def rank_by_asset_class(entries: tuple[ScoreEntry, ...]) -> dict[str, tuple[str, ...]]:
    """Return deterministic ranking per asset class."""

    _validate_entries(entries)

    grouped: dict[str, list[ScoreEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.asset_class, []).append(entry)

    ranking: dict[str, tuple[str, ...]] = {}
    for asset_class, values in grouped.items():
        ordered = sorted(values, key=lambda value: (-value.score, value.manager_id))
        ranking[asset_class] = tuple(value.manager_id for value in ordered)
    return ranking


def detect_score_drift(
    baseline: tuple[ScoreEntry, ...],
    candidate: tuple[ScoreEntry, ...],
    *,
    max_score_delta: float = 0.05,
    max_rank_movement: int = 1,
) -> DriftReport:
    """Detect rank and score drift above configurable thresholds."""

    if max_score_delta < 0:
        raise ValueError("max_score_delta must be >= 0")
    if max_rank_movement < 0:
        raise ValueError("max_rank_movement must be >= 0")

    _validate_entries(baseline)
    _validate_entries(candidate)
    baseline_lookup = _build_lookup(baseline)
    candidate_lookup = _build_lookup(candidate)

    if set(baseline_lookup) != set(candidate_lookup):
        raise ValueError("baseline and candidate must contain the same manager+asset-class keys")

    baseline_rank = _rank_positions(baseline)
    candidate_rank = _rank_positions(candidate)
    alerts: list[DriftAlert] = []

    for key, baseline_entry in baseline_lookup.items():
        candidate_entry = candidate_lookup[key]
        score_delta = abs(candidate_entry.score - baseline_entry.score)
        rank_movement = abs(candidate_rank[key] - baseline_rank[key])
        reasons: list[str] = []
        if score_delta > max_score_delta:
            reasons.append("score_delta")
        if rank_movement > max_rank_movement:
            reasons.append("rank_movement")
        if reasons:
            alerts.append(
                DriftAlert(
                    manager_id=key[0],
                    asset_class=key[1],
                    score_delta=score_delta,
                    rank_movement=rank_movement,
                    reasons=tuple(reasons),
                )
            )

    ordered_alerts = tuple(sorted(alerts, key=lambda alert: (alert.asset_class, alert.manager_id)))
    return DriftReport(
        alerts=ordered_alerts,
        checked_count=len(baseline_lookup),
        max_score_delta_threshold=max_score_delta,
        max_rank_movement_threshold=max_rank_movement,
    )


def build_calibration_stats(entries: tuple[ScoreEntry, ...]) -> tuple[CalibrationStats, ...]:
    """Build per-asset-class score distribution summaries."""

    _validate_entries(entries)
    grouped: dict[str, list[float]] = {}
    for entry in entries:
        grouped.setdefault(entry.asset_class, []).append(entry.score)

    summaries: list[CalibrationStats] = []
    for asset_class in sorted(grouped):
        values = sorted(grouped[asset_class])
        summaries.append(
            CalibrationStats(
                asset_class=asset_class,
                count=len(values),
                mean=_mean(values),
                stddev=_stddev(values),
                minimum=values[0],
                p50=_percentile(values, 0.50),
                p90=_percentile(values, 0.90),
                maximum=values[-1],
            )
        )
    return tuple(summaries)


def _validate_entries(entries: tuple[ScoreEntry, ...]) -> None:
    if not entries:
        raise ValueError("entries must contain at least one score")
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not entry.manager_id:
            raise ValueError("manager_id must be non-empty")
        if not entry.asset_class:
            raise ValueError("asset_class must be non-empty")
        if not 0.0 <= entry.score <= 1.0:
            raise ValueError("score must be between 0 and 1")
        key = (entry.manager_id, entry.asset_class)
        if key in seen:
            raise ValueError(
                f"duplicate score entry for manager={entry.manager_id}, asset={entry.asset_class}"
            )
        seen.add(key)


def _build_lookup(entries: tuple[ScoreEntry, ...]) -> dict[tuple[str, str], ScoreEntry]:
    return {(entry.manager_id, entry.asset_class): entry for entry in entries}


def _rank_positions(entries: tuple[ScoreEntry, ...]) -> dict[tuple[str, str], int]:
    grouped: dict[str, list[ScoreEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.asset_class, []).append(entry)

    positions: dict[tuple[str, str], int] = {}
    for asset_class, values in grouped.items():
        ordered = sorted(values, key=lambda value: (-value.score, value.manager_id))
        for idx, entry in enumerate(ordered, start=1):
            positions[(entry.manager_id, asset_class)] = idx
    return positions


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return sqrt(variance)


def _percentile(values: list[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * fraction
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    weight = index - lo
    return values[lo] * (1.0 - weight) + values[hi] * weight
