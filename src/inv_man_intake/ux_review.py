"""Configurable UX review scoring and blocking policy."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "ux_review_policy.json"


@dataclass(frozen=True)
class UXReviewPolicy:
    schema_version: str
    effective_date: date
    review_by: date
    review_after_completed_reviews: int
    pass_threshold: float
    weights: Mapping[str, float]
    severity_4_categories: frozenset[str]


@dataclass(frozen=True)
class UXFinding:
    category: str
    severity: int
    summary: str = ""


@dataclass(frozen=True)
class UXReviewResult:
    overall_score: float
    passes: bool
    severity_4_categories: tuple[str, ...]
    policy_review_due: bool
    policy_schema_version: str


def load_ux_review_policy(path: Path = DEFAULT_POLICY_PATH) -> UXReviewPolicy:
    """Load and validate the repository-owned UX review policy."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    weights = {str(name): float(value) for name, value in payload["weights"].items()}
    expected_weights = {"usability", "adversarial", "owner_calibration"}
    if set(weights) != expected_weights:
        raise ValueError(f"weights must contain exactly {sorted(expected_weights)}")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("UX review weights must sum to 1.0")
    if any(weight < 0.0 for weight in weights.values()):
        raise ValueError("UX review weights cannot be negative")

    pass_threshold = float(payload["pass_threshold"])
    if not 0.0 <= pass_threshold <= 10.0:
        raise ValueError("pass_threshold must be between 0 and 10")

    review_after = int(payload["review_after_completed_reviews"])
    if review_after <= 0:
        raise ValueError("review_after_completed_reviews must be positive")

    categories = frozenset(str(value) for value in payload["severity_4_categories"])
    if not categories:
        raise ValueError("severity_4_categories cannot be empty")

    return UXReviewPolicy(
        schema_version=str(payload["schema_version"]),
        effective_date=date.fromisoformat(str(payload["effective_date"])),
        review_by=date.fromisoformat(str(payload["review_by"])),
        review_after_completed_reviews=review_after,
        pass_threshold=pass_threshold,
        weights=weights,
        severity_4_categories=categories,
    )


def evaluate_ux_review(
    *,
    usability_score: float,
    adversarial_score: float,
    owner_calibration_score: float,
    findings: Sequence[UXFinding] = (),
    completed_reviews: int = 0,
    as_of: date | None = None,
    policy: UXReviewPolicy | None = None,
) -> UXReviewResult:
    """Score a UX review and apply severity-4 and policy-review gates."""

    active_policy = policy or load_ux_review_policy()
    scores = {
        "usability": float(usability_score),
        "adversarial": float(adversarial_score),
        "owner_calibration": float(owner_calibration_score),
    }
    for name, score in scores.items():
        if not 0.0 <= score <= 10.0:
            raise ValueError(f"{name}_score must be between 0 and 10")
    if completed_reviews < 0:
        raise ValueError("completed_reviews cannot be negative")

    invalid_severity = [
        finding.severity for finding in findings if finding.severity not in range(1, 5)
    ]
    if invalid_severity:
        raise ValueError("finding severity must be between 1 and 4")
    unknown_severity_4 = sorted(
        {
            finding.category
            for finding in findings
            if finding.severity == 4 and finding.category not in active_policy.severity_4_categories
        }
    )
    if unknown_severity_4:
        raise ValueError(
            "severity-4 finding categories must be configured: " + ", ".join(unknown_severity_4)
        )

    severity_4 = tuple(
        sorted(
            {
                finding.category
                for finding in findings
                if finding.severity == 4 and finding.category in active_policy.severity_4_categories
            }
        )
    )
    overall = sum(scores[name] * active_policy.weights[name] for name in scores)
    review_date = as_of or date.today()
    review_due = (
        review_date >= active_policy.review_by
        or completed_reviews >= active_policy.review_after_completed_reviews
    )

    return UXReviewResult(
        overall_score=round(overall, 4),
        passes=overall >= active_policy.pass_threshold and not severity_4,
        severity_4_categories=severity_4,
        policy_review_due=review_due,
        policy_schema_version=active_policy.schema_version,
    )
