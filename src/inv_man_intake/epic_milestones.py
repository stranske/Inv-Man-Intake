"""Milestone ordering and dependency gates for v1 child issues."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Milestone = Literal["A", "B", "C", "D"]

_MILESTONE_ORDER: tuple[Milestone, ...] = ("A", "B", "C", "D")


@dataclass(frozen=True)
class ChildIssue:
    """A child issue in the v1 epic dependency graph."""

    issue_number: int
    title: str
    milestone: Milestone
    depends_on: tuple[int, ...] = ()


_CHILD_ISSUES: tuple[ChildIssue, ...] = (
    ChildIssue(
        issue_number=8,
        title="Intake and document registry",
        milestone="A",
    ),
    ChildIssue(
        issue_number=11,
        title="Core schema and storage contracts",
        milestone="A",
        depends_on=(8,),
    ),
    ChildIssue(
        issue_number=15,
        title="LangSmith tracing + operational baseline",
        milestone="A",
        depends_on=(8,),
    ),
    ChildIssue(
        issue_number=9,
        title="Extraction confidence + fallback routing",
        milestone="B",
        depends_on=(8, 11, 15),
    ),
    ChildIssue(
        issue_number=10,
        title="Image intelligence + user feedback loop",
        milestone="B",
        depends_on=(9,),
    ),
    ChildIssue(
        issue_number=14,
        title="Validation queue ownership + workflow states",
        milestone="B",
        depends_on=(9,),
    ),
    ChildIssue(
        issue_number=12,
        title="Performance normalization + conflict rules",
        milestone="C",
        depends_on=(9, 11, 15),
    ),
    ChildIssue(
        issue_number=13,
        title="Asset-class scoring + explainability output",
        milestone="D",
        depends_on=(12, 14),
    ),
)


def child_issue_plan() -> tuple[ChildIssue, ...]:
    """Return the canonical ordered child issue plan for v1."""

    return _CHILD_ISSUES


def validate_child_issue_plan(plan: tuple[ChildIssue, ...] | None = None) -> tuple[str, ...]:
    """Validate milestone ordering and dependency references for a child issue plan."""

    issues = plan if plan is not None else _CHILD_ISSUES
    errors: list[str] = []

    issue_numbers = [item.issue_number for item in issues]
    if len(issue_numbers) != len(set(issue_numbers)):
        errors.append("Duplicate child issue numbers are not allowed")

    by_issue = {item.issue_number: item for item in issues}
    order_index = {milestone: index for index, milestone in enumerate(_MILESTONE_ORDER)}

    for issue in issues:
        for dependency in issue.depends_on:
            if dependency not in by_issue:
                errors.append(f"Issue #{issue.issue_number} depends on unknown issue #{dependency}")
                continue

            dependency_issue = by_issue[dependency]
            if order_index[dependency_issue.milestone] > order_index[issue.milestone]:
                errors.append(
                    f"Issue #{issue.issue_number} depends on later milestone "
                    f"{dependency_issue.milestone} issue #{dependency}"
                )

    return tuple(errors)


def next_ready_issues(completed_issue_numbers: set[int]) -> tuple[ChildIssue, ...]:
    """Return next unblocked child issues based on milestone and dependency gates."""

    current_milestone = _next_open_milestone(completed_issue_numbers)
    if current_milestone is None:
        return ()

    ready: list[ChildIssue] = []
    for issue in _CHILD_ISSUES:
        if issue.issue_number in completed_issue_numbers:
            continue
        if issue.milestone != current_milestone:
            continue
        if all(dependency in completed_issue_numbers for dependency in issue.depends_on):
            ready.append(issue)
    return tuple(ready)


def _next_open_milestone(completed_issue_numbers: set[int]) -> Milestone | None:
    for milestone in _MILESTONE_ORDER:
        milestone_issues = [item for item in _CHILD_ISSUES if item.milestone == milestone]
        if any(issue.issue_number not in completed_issue_numbers for issue in milestone_issues):
            return milestone
    return None
