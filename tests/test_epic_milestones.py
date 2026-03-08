"""Tests for milestone ordering and dependency gates across child issues."""

from __future__ import annotations

from inv_man_intake.epic_milestones import (
    ChildIssue,
    child_issue_plan,
    next_ready_issues,
    validate_child_issue_plan,
)


def test_child_issue_plan_contains_expected_child_issue_numbers() -> None:
    issue_numbers = {item.issue_number for item in child_issue_plan()}
    assert issue_numbers == {8, 9, 10, 11, 12, 13, 14, 15}


def test_canonical_plan_passes_validation() -> None:
    assert validate_child_issue_plan() == ()


def test_ready_issues_progress_by_milestone_and_dependencies() -> None:
    ready = next_ready_issues(set())
    assert {item.issue_number for item in ready} == {8}

    ready = next_ready_issues({8})
    assert {item.issue_number for item in ready} == {11, 15}

    ready = next_ready_issues({8, 11, 15})
    assert {item.issue_number for item in ready} == {9}

    ready = next_ready_issues({8, 9, 11, 15})
    assert {item.issue_number for item in ready} == {10, 14}

    ready = next_ready_issues({8, 9, 10, 11, 14, 15})
    assert {item.issue_number for item in ready} == {12}

    ready = next_ready_issues({8, 9, 10, 11, 12, 14, 15})
    assert {item.issue_number for item in ready} == {13}


def test_later_milestone_blocked_until_current_milestone_completes() -> None:
    ready = next_ready_issues({8, 11})
    assert {item.issue_number for item in ready} == {15}
    assert all(item.milestone == "A" for item in ready)


def test_validation_rejects_dependency_on_later_milestone() -> None:
    invalid_plan = (
        ChildIssue(issue_number=1, title="A", milestone="A"),
        ChildIssue(issue_number=2, title="D", milestone="D", depends_on=(1,)),
        ChildIssue(issue_number=3, title="B", milestone="B", depends_on=(2,)),
    )
    errors = validate_child_issue_plan(invalid_plan)
    assert any("depends on later milestone" in error for error in errors)
