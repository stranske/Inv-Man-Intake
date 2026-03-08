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
from inv_man_intake.scoring.explainability import (
    ExplainabilityPayload,
    ScoreComponentInput,
    ScoreComponentOutput,
    build_explainability_payload,
    format_explainability_payload,
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
from inv_man_intake.scoring.weights import (
    COMPONENT_NAMES,
    LAUNCH_ASSET_CLASSES,
    ScoringWeightSet,
    get_weight_set,
    load_weight_registry,
)

__all__ = [
    "COMPONENT_NAMES",
    "CalibrationStats",
    "DriftAlert",
    "DriftReport",
    "ExplainabilityPayload",
    "LAUNCH_ASSET_CLASSES",
    "RedFlagDecision",
    "RedFlagHook",
    "ScoringWeightSet",
    "ScoreComponent",
    "ScoreComponentInput",
    "ScoreComponentOutput",
    "ScoreEntry",
    "ScoreResult",
    "ScoreSubmission",
    "build_explainability_payload",
    "build_calibration_stats",
    "compute_score",
    "default_weights_by_asset_class",
    "detect_score_drift",
    "format_explainability_payload",
    "get_weight_set",
    "load_weight_registry",
    "rank_by_asset_class",
]
