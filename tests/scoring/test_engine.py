"""Tests for deterministic scoring engine behavior."""

from __future__ import annotations

import pytest

from inv_man_intake.scoring.contracts import RedFlagDecision, ScoreComponent, ScoreSubmission
from inv_man_intake.scoring.engine import compute_score


def _submission(asset_class: str) -> ScoreSubmission:
    return ScoreSubmission(
        manager_id="mgr_001",
        asset_class=asset_class,
        components=(
            ScoreComponent("performance_consistency", 0.80),
            ScoreComponent("risk_adjusted_returns", 0.60),
            ScoreComponent("operational_quality", 0.90),
            ScoreComponent("transparency", 0.70),
            ScoreComponent("team_experience", 0.50),
        ),
    )


def test_compute_score_is_deterministic_for_identical_inputs() -> None:
    submission = _submission("equity")

    first = compute_score(submission)
    second = compute_score(submission)

    assert first == second
    assert first.base_score == pytest.approx(0.705)
    assert first.final_score == first.base_score
    assert first.red_flag_applied is False


def test_asset_class_weight_sets_produce_materially_different_scores() -> None:
    equity = compute_score(_submission("equity"))
    credit = compute_score(_submission("credit"))

    assert equity.base_score == pytest.approx(0.705)
    assert credit.base_score == pytest.approx(0.715)
    assert credit.base_score != equity.base_score


def test_red_flag_hook_can_cap_score() -> None:
    class CapHook:
        def apply(self, submission: ScoreSubmission, *, base_score: float) -> RedFlagDecision:
            del submission, base_score
            return RedFlagDecision(capped_score=0.55, reason="gating-breach")

    result = compute_score(_submission("equity"), red_flag_hook=CapHook())

    assert result.base_score == pytest.approx(0.705)
    assert result.final_score == pytest.approx(0.55)
    assert result.red_flag_applied is True
    assert result.red_flag_reason == "gating-breach"


def test_red_flag_hook_can_fully_block_score() -> None:
    class BlockHook:
        def apply(self, submission: ScoreSubmission, *, base_score: float) -> RedFlagDecision:
            del submission, base_score
            return RedFlagDecision(blocked=True, reason="compliance-block")

    result = compute_score(_submission("macro"), red_flag_hook=BlockHook())

    assert result.base_score == pytest.approx(0.691)
    assert result.final_score == pytest.approx(0.0)
    assert result.red_flag_applied is True
    assert result.red_flag_reason == "compliance-block"
