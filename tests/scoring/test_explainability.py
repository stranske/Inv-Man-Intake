"""Tests for scoring explainability payload contract and deterministic formatting."""

from __future__ import annotations

from math import nan
from typing import Any, cast

import pytest

from inv_man_intake.scoring.explainability import (
    ScoreComponentInput,
    build_explainability_payload,
    format_explainability_payload,
)


def test_build_payload_computes_component_contributions_and_reconciles_total() -> None:
    payload = build_explainability_payload(
        components=(
            ScoreComponentInput(
                component="alpha_quality",
                weight=0.4,
                score=0.75,
                rationale="Consistent alpha generation in lookback window.",
            ),
            ScoreComponentInput(
                component="risk_stability",
                weight=0.6,
                score=0.5,
                rationale="Drawdown profile within policy threshold.",
            ),
        )
    )

    assert payload.total_contribution == pytest.approx(0.6)
    assert payload.overall_score == pytest.approx(0.6)
    assert tuple(component.component for component in payload.components) == (
        "alpha_quality",
        "risk_stability",
    )


def test_build_payload_rejects_non_reconciling_overall_score() -> None:
    with pytest.raises(ValueError, match="overall_score does not reconcile"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=0.4,
                    score=0.75,
                    rationale="Consistent alpha generation in lookback window.",
                ),
                ScoreComponentInput(
                    component="risk_stability",
                    weight=0.6,
                    score=0.5,
                    rationale="Drawdown profile within policy threshold.",
                ),
            ),
            overall_score=0.65,
        )


def test_formatter_is_stable_for_unordered_input_components() -> None:
    payload = build_explainability_payload(
        components=(
            ScoreComponentInput(
                component="z_tail_risk",
                weight=0.3,
                score=0.8,
                rationale="Tail-risk controls improved this period.",
            ),
            ScoreComponentInput(
                component="a_liquidity",
                weight=0.7,
                score=0.4,
                rationale="Liquidity coverage remains moderate.",
            ),
        )
    )

    formatted_once = format_explainability_payload(payload)
    formatted_twice = format_explainability_payload(payload)

    assert formatted_once == formatted_twice
    components = cast(list[dict[str, Any]], formatted_once["components"])
    assert [entry["component"] for entry in components] == [
        "a_liquidity",
        "z_tail_risk",
    ]


def test_component_validations_enforced() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="risk_stability",
                    weight=0.5,
                    score=1.1,
                    rationale="Invalid score",
                ),
            )
        )


def test_build_payload_rejects_duplicate_component_identifiers() -> None:
    with pytest.raises(ValueError, match="component identifiers must be unique"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=0.4,
                    score=0.75,
                    rationale="Baseline rationale.",
                ),
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=0.6,
                    score=0.5,
                    rationale="Duplicate identifier.",
                ),
            )
        )


def test_build_payload_rejects_duplicate_component_identifiers_after_trimming() -> None:
    with pytest.raises(ValueError, match="component identifiers must be unique"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component=" alpha_quality ",
                    weight=0.4,
                    score=0.75,
                    rationale="Baseline rationale.",
                ),
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=0.6,
                    score=0.5,
                    rationale="Duplicate identifier.",
                ),
            )
        )


def test_build_payload_rejects_empty_components() -> None:
    with pytest.raises(ValueError, match="at least one component"):
        build_explainability_payload(components=())


def test_build_payload_rejects_whitespace_only_component_and_rationale() -> None:
    with pytest.raises(ValueError, match="component must be non-empty"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="   ",
                    weight=0.4,
                    score=0.75,
                    rationale="valid",
                ),
            )
        )

    with pytest.raises(ValueError, match="alpha_quality.rationale must be non-empty"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=0.4,
                    score=0.75,
                    rationale="   ",
                ),
            )
        )


def test_build_payload_rejects_negative_weight() -> None:
    with pytest.raises(ValueError, match="alpha_quality.weight must be >= 0"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=-0.01,
                    score=0.75,
                    rationale="valid",
                ),
            )
        )


def test_build_payload_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="overall_score must be finite"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=0.4,
                    score=0.75,
                    rationale="valid",
                ),
            ),
            overall_score=nan,
        )

    with pytest.raises(ValueError, match="alpha_quality.weight must be finite"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=nan,
                    score=0.75,
                    rationale="valid",
                ),
            )
        )

    with pytest.raises(ValueError, match="alpha_quality.score must be finite"):
        build_explainability_payload(
            components=(
                ScoreComponentInput(
                    component="alpha_quality",
                    weight=0.4,
                    score=nan,
                    rationale="valid",
                ),
            )
        )
