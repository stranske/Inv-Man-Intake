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
