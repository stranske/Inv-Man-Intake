"""Tests for deterministic peer-group percentile scoring."""

from __future__ import annotations

import pytest

from inv_man_intake.scoring.contracts import ScoreComponent, ScoreSubmission
from inv_man_intake.scoring.engine import compute_score
from inv_man_intake.scoring.peer_group import CohortScore, InMemoryCohortStore, percentile_rank


def _seeded_macro_cohort() -> InMemoryCohortStore:
    return InMemoryCohortStore(
        CohortScore(asset_class="macro", manager_id=manager_id, base_score=score)
        for manager_id, score in (
            ("macro_40", 0.40),
            ("macro_50", 0.50),
            ("macro_60", 0.60),
            ("macro_70", 0.70),
            ("macro_80", 0.80),
        )
    )


def _flat_submission(score: float = 0.60) -> ScoreSubmission:
    return ScoreSubmission(
        manager_id="candidate_macro",
        asset_class="macro",
        components=(
            ScoreComponent("performance_consistency", score),
            ScoreComponent("risk_adjusted_returns", score),
            ScoreComponent("operational_quality", score),
            ScoreComponent("transparency", score),
            ScoreComponent("team_experience", score),
        ),
    )


def test_percentile_rank_against_seeded_cohort() -> None:
    cohort = _seeded_macro_cohort()

    percentile = percentile_rank(0.60, "macro", cohort)
    repeated = percentile_rank(0.60, "macro", cohort)

    assert percentile == pytest.approx(50.0)
    assert repeated == percentile

    cohort.add_score("macro", "macro_90", 0.90)
    shifted_percentile = percentile_rank(0.60, "macro", cohort)

    assert shifted_percentile != pytest.approx(percentile)


def test_compute_score_exposes_peer_group_percentile_without_changing_final_score() -> None:
    result = compute_score(_flat_submission(), peer_group_store=_seeded_macro_cohort())

    assert result.final_score == pytest.approx(0.60)
    assert result.peer_group_percentile == pytest.approx(50.0)
    assert result.peer_group_size == 5


def test_percentile_rank_uses_midpoint_tie_rule() -> None:
    cohort = InMemoryCohortStore(
        (
            CohortScore(asset_class="macro", manager_id="a", base_score=0.50),
            CohortScore(asset_class="macro", manager_id="b", base_score=0.60),
            CohortScore(asset_class="macro", manager_id="c", base_score=0.60),
            CohortScore(asset_class="macro", manager_id="d", base_score=0.80),
        )
    )

    assert percentile_rank(0.60, "macro", cohort) == pytest.approx(50.0)


def test_cohort_store_overwrites_existing_manager_score() -> None:
    cohort = InMemoryCohortStore(
        (
            CohortScore(asset_class="macro", manager_id="manager_a", base_score=0.40),
            CohortScore(asset_class="macro", manager_id="manager_b", base_score=0.60),
            CohortScore(asset_class="macro", manager_id="manager_a", base_score=0.80),
        )
    )

    assert cohort.scores_for_asset_class("macro") == pytest.approx((0.80, 0.60))


def test_percentile_rank_treats_rounding_noise_as_tie() -> None:
    cohort = InMemoryCohortStore(
        (
            CohortScore(asset_class="macro", manager_id="a", base_score=0.50),
            CohortScore(asset_class="macro", manager_id="b", base_score=0.1 + 0.2 + 0.3),
            CohortScore(asset_class="macro", manager_id="c", base_score=0.60),
            CohortScore(asset_class="macro", manager_id="d", base_score=0.80),
        )
    )

    assert percentile_rank(0.60, "macro", cohort) == pytest.approx(50.0)


def test_peer_group_rejects_invalid_scores() -> None:
    with pytest.raises(ValueError, match="base_score must be between 0 and 1"):
        InMemoryCohortStore((CohortScore(asset_class="macro", manager_id="bad", base_score=1.01),))

    with pytest.raises(ValueError, match="cohort is empty for asset class"):
        percentile_rank(0.50, "macro", InMemoryCohortStore())

    with pytest.raises(ValueError, match="score must be between 0 and 1"):
        percentile_rank(1.01, "macro", _seeded_macro_cohort())

    with pytest.raises(ValueError, match="score must be finite"):
        percentile_rank(float("nan"), "macro", _seeded_macro_cohort())
