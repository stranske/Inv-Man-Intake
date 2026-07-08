"""Deterministic UX review gate for the operator packet frontend."""

from __future__ import annotations

from dataclasses import dataclass

from frontend_verify import FrontendVerificationResult, default_upload, run_frontend_verifier


@dataclass(frozen=True)
class UXReviewFixture:
    name: str
    usability_score: float
    severity_4_blockers: tuple[str, ...] = ()
    adversarial: bool = False


@dataclass(frozen=True)
class UXReviewResult:
    fixture: UXReviewFixture
    frontend: FrontendVerificationResult
    passed: bool
    reasons: tuple[str, ...]


def run_ux_review(fixture: UXReviewFixture) -> UXReviewResult:
    frontend = run_frontend_verifier(
        uploads=(default_upload(),),
        open_first_graphic=not fixture.adversarial,
        graphic_click_handler_enabled=not fixture.adversarial,
    )
    reasons: list[str] = []
    if fixture.usability_score < 7.0:
        reasons.append(f"usability score {fixture.usability_score:.1f} is below 7.0")
    if fixture.severity_4_blockers:
        reasons.extend(f"severity-4 blocker: {blocker}" for blocker in fixture.severity_4_blockers)
    if frontend.outbound_requests != 0:
        reasons.append("frontend attempted outbound requests")
    if not frontend.has_node(role="file-upload", name="Packet upload"):
        reasons.append("packet upload control missing")
    if not fixture.adversarial and not frontend.has_node(
        role="cell", name="Status", value="Opened"
    ):
        reasons.append("graphics detail state did not open")

    return UXReviewResult(
        fixture=fixture,
        frontend=frontend,
        passed=not reasons,
        reasons=tuple(reasons),
    )


def assert_ux_review_passes(fixture: UXReviewFixture) -> UXReviewResult:
    result = run_ux_review(fixture)
    if not result.passed:
        raise AssertionError("; ".join(result.reasons))
    return result
