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
    submission = _submission("equity_market_neutral")

    first = compute_score(submission)
    second = compute_score(submission)

    assert first == second
    assert first.base_score == pytest.approx(0.705)
    assert first.final_score == first.base_score
    assert first.red_flag_applied is False


def test_asset_class_weight_sets_produce_materially_different_scores() -> None:
    equity = compute_score(_submission("equity_market_neutral"))
    credit = compute_score(_submission("credit_long_short"))

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
    assert result.asset_class == "equity_market_neutral"
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


def test_red_flag_block_applies_when_base_score_is_zero() -> None:
    class BlockHook:
        def apply(self, submission: ScoreSubmission, *, base_score: float) -> RedFlagDecision:
            del submission, base_score
            return RedFlagDecision(blocked=True, reason="zero-block")

    submission = ScoreSubmission(
        manager_id="mgr_zero",
        asset_class="macro",
        components=(
            ScoreComponent("performance_consistency", 0.0),
            ScoreComponent("risk_adjusted_returns", 0.0),
            ScoreComponent("operational_quality", 0.0),
            ScoreComponent("transparency", 0.0),
            ScoreComponent("team_experience", 0.0),
        ),
    )

    result = compute_score(submission, red_flag_hook=BlockHook())

    assert result.base_score == pytest.approx(0.0)
    assert result.final_score == pytest.approx(0.0)
    assert result.red_flag_applied is True
    assert result.red_flag_reason == "zero-block"


def test_red_flag_cap_at_or_above_base_does_not_apply_reason() -> None:
    class CapHook:
        def apply(self, submission: ScoreSubmission, *, base_score: float) -> RedFlagDecision:
            del submission, base_score
            return RedFlagDecision(capped_score=0.95, reason="not-lower")

    result = compute_score(_submission("equity"), red_flag_hook=CapHook())

    assert result.base_score == pytest.approx(0.705)
    assert result.final_score == pytest.approx(result.base_score)
    assert result.red_flag_applied is False
    assert result.red_flag_reason is None


@pytest.mark.parametrize(
    "invalid_cap",
    [-0.01, 1.01],
    ids=["below_zero", "above_one"],
)
def test_capped_score_bounds_rejects_invalid_red_flag_cap(invalid_cap: float) -> None:
    class InvalidCapHook:
        def apply(self, submission: ScoreSubmission, *, base_score: float) -> RedFlagDecision:
            del submission, base_score
            return RedFlagDecision(capped_score=invalid_cap, reason="invalid-cap")

    with pytest.raises(ValueError, match="red flag capped_score must be between 0 and 1"):
        compute_score(_submission("equity"), red_flag_hook=InvalidCapHook())


def test_compute_score_rejects_unmapped_asset_class() -> None:
    with pytest.raises(ValueError, match="unknown asset class: real_assets"):
        compute_score(_submission("real_assets"))


def test_compute_score_reports_missing_canonical_weight_set_for_alias() -> None:
    with pytest.raises(
        ValueError,
        match=(
            "missing weight set for canonical asset class 'equity_market_neutral' "
            "from input 'equity'"
        ),
    ):
        compute_score(_submission("equity"), weights_by_asset_class={"macro": {}})


def _valid_weights() -> dict[str, float]:
    return {
        "performance_consistency": 0.30,
        "risk_adjusted_returns": 0.25,
        "operational_quality": 0.15,
        "transparency": 0.15,
        "team_experience": 0.15,
    }


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_compute_score_rejects_non_finite_component(bad: float) -> None:
    submission = ScoreSubmission(
        manager_id="mgr_nan",
        asset_class="equity_market_neutral",
        components=(
            ScoreComponent("performance_consistency", bad),
            ScoreComponent("risk_adjusted_returns", 0.60),
            ScoreComponent("operational_quality", 0.90),
            ScoreComponent("transparency", 0.70),
            ScoreComponent("team_experience", 0.50),
        ),
    )
    with pytest.raises(ValueError, match="component performance_consistency must be finite"):
        compute_score(submission)


def test_compute_score_rejects_non_finite_weight() -> None:
    weights = _valid_weights()
    weights["risk_adjusted_returns"] = float("nan")
    with pytest.raises(ValueError, match="weight risk_adjusted_returns must be finite"):
        compute_score(
            _submission("equity_market_neutral"),
            weights_by_asset_class={"equity_market_neutral": weights},
        )


def test_compute_score_rejects_non_finite_cap() -> None:
    class NanCapHook:
        def apply(self, submission: ScoreSubmission, *, base_score: float) -> RedFlagDecision:
            return RedFlagDecision(capped_score=float("nan"), reason="bad-cap")

    with pytest.raises(ValueError, match="red flag capped_score must be finite"):
        compute_score(_submission("equity_market_neutral"), red_flag_hook=NanCapHook())
