"""Scoring engine and regression helpers."""

from inv_man_intake.scoring.contracts import (
    RedFlagDecision,
    ScoreComponent,
    ScoreResult,
    ScoreSubmission,
)
from inv_man_intake.scoring.engine import (
    RedFlagHook,
    compute_score,
    default_weights_by_asset_class,
)
from inv_man_intake.scoring.regression import (
    CalibrationStats,
    DriftAlert,
    DriftReport,
    ScoreEntry,
    build_calibration_stats,
    detect_score_drift,
    rank_by_asset_class,
)

__all__ = [
    "CalibrationStats",
    "DriftAlert",
    "DriftReport",
    "RedFlagDecision",
    "RedFlagHook",
    "ScoreComponent",
    "ScoreEntry",
    "ScoreResult",
    "ScoreSubmission",
    "build_calibration_stats",
    "compute_score",
    "default_weights_by_asset_class",
    "detect_score_drift",
    "rank_by_asset_class",
]
