from __future__ import annotations

import pytest

from ux_review import UXReviewFixture, assert_ux_review_passes, run_ux_review


def test_ux_review_normal_path_passes_with_calibrated_score() -> None:
    result = assert_ux_review_passes(
        UXReviewFixture(name="owner-calibrated-normal", usability_score=8.2)
    )

    assert result.frontend.has_node(role="cell", name="Status", value="Opened")


def test_ux_review_adversarial_path_records_broken_gallery_state() -> None:
    result = run_ux_review(
        UXReviewFixture(name="adversarial-gallery-disabled", usability_score=7.4, adversarial=True)
    )

    assert result.passed
    assert not result.frontend.has_node(role="cell", name="Status", value="Opened")


def test_ux_review_fails_below_owner_calibration_threshold() -> None:
    with pytest.raises(AssertionError, match="below 7.0"):
        assert_ux_review_passes(UXReviewFixture(name="low-score", usability_score=6.9))


def test_ux_review_fails_on_severity_four_blocker() -> None:
    result = run_ux_review(
        UXReviewFixture(
            name="blocked",
            usability_score=8.0,
            severity_4_blockers=("core workflow cannot complete",),
        )
    )

    assert result.passed is False
    assert "severity-4 blocker: core workflow cannot complete" in result.reasons
