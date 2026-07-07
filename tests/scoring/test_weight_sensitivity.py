"""Tests for weight sensitivity reporting."""

from __future__ import annotations

import pytest

from inv_man_intake.scoring.contracts import ScoreComponent, ScoreSubmission
from inv_man_intake.scoring.weight_sensitivity import weight_sensitivity_report


def _submission(
    manager_id: str,
    *,
    performance_consistency: float,
    risk_adjusted_returns: float,
    operational_quality: float = 0.50,
    transparency: float = 0.50,
    team_experience: float = 0.50,
) -> ScoreSubmission:
    return ScoreSubmission(
        manager_id=manager_id,
        asset_class="equity_market_neutral",
        components=(
            ScoreComponent("performance_consistency", performance_consistency),
            ScoreComponent("risk_adjusted_returns", risk_adjusted_returns),
            ScoreComponent("operational_quality", operational_quality),
            ScoreComponent("transparency", transparency),
            ScoreComponent("team_experience", team_experience),
        ),
    )


def test_perturbation_changes_ranking_deterministically() -> None:
    cohort = (
        _submission("steady_performer", performance_consistency=0.90, risk_adjusted_returns=0.40),
        _submission("return_leader", performance_consistency=0.60, risk_adjusted_returns=0.75),
        _submission("balanced_peer", performance_consistency=0.70, risk_adjusted_returns=0.55),
    )

    report = weight_sensitivity_report(
        cohort,
        "equity",
        {"risk_adjusted_returns": 0.05},
    )

    assert report.asset_class == "equity_market_neutral"
    assert sum(report.perturbed_weights.values()) == pytest.approx(1.0)
    assert (
        report.perturbed_weights["risk_adjusted_returns"]
        > report.baseline_weights["risk_adjusted_returns"]
    )

    rows = {row.manager_id: row for row in report.rows}
    assert rows["steady_performer"].baseline_rank == 1
    assert rows["steady_performer"].perturbed_rank == 2
    assert rows["steady_performer"].rank_delta == -1
    assert rows["return_leader"].baseline_rank == 2
    assert rows["return_leader"].perturbed_rank == 1
    assert rows["return_leader"].rank_delta == 1
    assert rows["return_leader"].score_delta > rows["steady_performer"].score_delta
    assert [row.manager_id for row in report.rows] == [
        "steady_performer",
        "return_leader",
        "balanced_peer",
    ]


def test_unknown_perturbation_component_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown perturbation component"):
        weight_sensitivity_report(
            (
                _submission(
                    "steady_performer",
                    performance_consistency=0.90,
                    risk_adjusted_returns=0.45,
                ),
            ),
            "equity_market_neutral",
            {"unknown_component": 0.05},
        )
