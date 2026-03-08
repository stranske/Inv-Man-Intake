"""Tests for v1 child issue contract validation."""

from __future__ import annotations

from inv_man_intake.epic_issue_contracts import (
    ChildIssueContract,
    child_issue_contracts,
    validate_child_issue_contracts,
)


def test_canonical_child_issue_contracts_pass_validation() -> None:
    assert validate_child_issue_contracts() == ()


def test_validation_rejects_missing_child_issue() -> None:
    contracts = tuple(item for item in child_issue_contracts() if item.issue_number != 10)
    errors = validate_child_issue_contracts(contracts)

    assert any("Missing child issue contracts" in error for error in errors)


def test_validation_rejects_mixed_parent_epic_links() -> None:
    contracts = list(child_issue_contracts())
    contracts[0] = ChildIssueContract(
        issue_number=contracts[0].issue_number,
        title=contracts[0].title,
        epic_ref="another-epic",
        sections=contracts[0].sections,
    )
    errors = validate_child_issue_contracts(tuple(contracts))

    assert any("same parent epic" in error for error in errors)


def test_validation_rejects_uniform_wrong_parent_epic_link() -> None:
    contracts = tuple(
        ChildIssueContract(
            issue_number=item.issue_number,
            title=item.title,
            epic_ref="some-other-epic",
            sections=item.sections,
        )
        for item in child_issue_contracts()
    )
    errors = validate_child_issue_contracts(contracts)

    assert any("must link to epic #7" in error for error in errors)


def test_validation_rejects_wrong_epic_link_for_single_child_issue() -> None:
    contracts = list(child_issue_contracts())
    contracts[3] = ChildIssueContract(
        issue_number=contracts[3].issue_number,
        title=contracts[3].title,
        epic_ref="other-epic-ref",
        sections=contracts[3].sections,
    )
    errors = validate_child_issue_contracts(tuple(contracts))

    assert any(
        f"Issue #{contracts[3].issue_number} is linked to wrong epic ref" in error
        for error in errors
    )


def test_validation_rejects_missing_required_issue_sections() -> None:
    contracts = list(child_issue_contracts())
    contracts[0] = ChildIssueContract(
        issue_number=contracts[0].issue_number,
        title=contracts[0].title,
        epic_ref=contracts[0].epic_ref,
        sections=("Why", "Scope", "Tasks"),
    )
    errors = validate_child_issue_contracts(tuple(contracts))

    assert any("missing required sections" in error for error in errors)


def test_validation_rejects_missing_scope_boundaries() -> None:
    contracts = list(child_issue_contracts())
    contracts[1] = ChildIssueContract(
        issue_number=contracts[1].issue_number,
        title=contracts[1].title,
        epic_ref=contracts[1].epic_ref,
        sections=contracts[1].sections,
        scope_boundaries=(),
        non_goals=contracts[1].non_goals,
        tasks=contracts[1].tasks,
        acceptance_criteria=contracts[1].acceptance_criteria,
    )
    errors = validate_child_issue_contracts(tuple(contracts))

    assert any("must define explicit scope boundaries" in error for error in errors)


def test_validation_rejects_non_actionable_tasks() -> None:
    contracts = list(child_issue_contracts())
    contracts[2] = ChildIssueContract(
        issue_number=contracts[2].issue_number,
        title=contracts[2].title,
        epic_ref=contracts[2].epic_ref,
        sections=contracts[2].sections,
        scope_boundaries=contracts[2].scope_boundaries,
        non_goals=contracts[2].non_goals,
        tasks=("Things", "Stuff"),
        acceptance_criteria=contracts[2].acceptance_criteria,
    )
    errors = validate_child_issue_contracts(tuple(contracts))

    assert any("non-actionable tasks" in error for error in errors)


def test_validation_rejects_non_testable_acceptance_criteria() -> None:
    contracts = list(child_issue_contracts())
    contracts[4] = ChildIssueContract(
        issue_number=contracts[4].issue_number,
        title=contracts[4].title,
        epic_ref=contracts[4].epic_ref,
        sections=contracts[4].sections,
        scope_boundaries=contracts[4].scope_boundaries,
        non_goals=contracts[4].non_goals,
        tasks=contracts[4].tasks,
        acceptance_criteria=("Quality is high", "Everything works"),
    )
    errors = validate_child_issue_contracts(tuple(contracts))

    assert any("non-testable acceptance criteria" in error for error in errors)
