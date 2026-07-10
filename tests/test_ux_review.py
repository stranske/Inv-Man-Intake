from datetime import date

import pytest

from inv_man_intake.ux_review import (
    UXFinding,
    evaluate_ux_review,
    load_ux_review_policy,
)


def test_policy_passes_weighted_score_at_threshold() -> None:
    result = evaluate_ux_review(
        usability_score=7.0,
        adversarial_score=8.0,
        owner_calibration_score=6.0,
        as_of=date(2026, 7, 10),
    )

    assert result.overall_score == 7.1
    assert result.passes is True
    assert result.severity_4_categories == ()
    assert result.policy_review_due is False


def test_configured_severity_4_blocks_high_score() -> None:
    result = evaluate_ux_review(
        usability_score=9.5,
        adversarial_score=9.5,
        owner_calibration_score=9.5,
        findings=[
            UXFinding(
                category="core_accessibility_blocker",
                severity=4,
                summary="Keyboard users cannot submit the intake form",
            )
        ],
        as_of=date(2026, 7, 10),
    )

    assert result.overall_score == 9.5
    assert result.passes is False
    assert result.severity_4_categories == ("core_accessibility_blocker",)


@pytest.mark.parametrize(
    ("completed_reviews", "as_of"),
    [
        (20, date(2026, 7, 10)),
        (0, date(2026, 10, 15)),
    ],
)
def test_policy_review_becomes_due_by_volume_or_date(completed_reviews: int, as_of: date) -> None:
    result = evaluate_ux_review(
        usability_score=8.0,
        adversarial_score=8.0,
        owner_calibration_score=8.0,
        completed_reviews=completed_reviews,
        as_of=as_of,
    )

    assert result.passes is True
    assert result.policy_review_due is True


def test_policy_rejects_out_of_range_score() -> None:
    with pytest.raises(ValueError, match="usability_score"):
        evaluate_ux_review(
            usability_score=10.1,
            adversarial_score=8.0,
            owner_calibration_score=8.0,
        )


def test_policy_rejects_unclassified_severity_4_finding() -> None:
    with pytest.raises(ValueError, match="must be configured"):
        evaluate_ux_review(
            usability_score=8.0,
            adversarial_score=8.0,
            owner_calibration_score=8.0,
            findings=[UXFinding(category="new_critical_category", severity=4)],
        )


def test_repository_policy_has_expected_version_and_review_date() -> None:
    policy = load_ux_review_policy()

    assert policy.schema_version == "ux-review-policy/v1"
    assert policy.review_by == date(2026, 10, 15)
    assert sum(policy.weights.values()) == pytest.approx(1.0)
