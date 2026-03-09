"""Scoring engine contracts and helpers."""

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

__all__ = [
    "RedFlagDecision",
    "RedFlagHook",
    "ScoreComponent",
    "ScoreResult",
    "ScoreSubmission",
    "compute_score",
    "default_weights_by_asset_class",
]
