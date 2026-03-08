"""Contract validation for v1 epic child issues."""

from __future__ import annotations

from dataclasses import dataclass

from inv_man_intake.epic_milestones import child_issue_plan

REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS: tuple[str, ...] = (
    "Why",
    "Scope",
    "Non-Goals",
    "Tasks",
    "Acceptance Criteria",
)


@dataclass(frozen=True)
class ChildIssueContract:
    """Canonical contract for each v1 child issue."""

    issue_number: int
    title: str
    epic_ref: str
    sections: tuple[str, ...]


_V1_EPIC_REF = "v1-single-execution-container"
V1_EPIC_ISSUE_NUMBER = 7


_CHILD_ISSUE_CONTRACTS: tuple[ChildIssueContract, ...] = (
    ChildIssueContract(
        issue_number=8,
        title="Intake and document registry",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
    ),
    ChildIssueContract(
        issue_number=9,
        title="Extraction confidence + fallback routing",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
    ),
    ChildIssueContract(
        issue_number=10,
        title="Image intelligence + user feedback loop",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
    ),
    ChildIssueContract(
        issue_number=11,
        title="Core schema and storage contracts",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
    ),
    ChildIssueContract(
        issue_number=12,
        title="Performance normalization + conflict rules",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
    ),
    ChildIssueContract(
        issue_number=13,
        title="Asset-class scoring + explainability output",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
    ),
    ChildIssueContract(
        issue_number=14,
        title="Validation queue ownership + workflow states",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
    ),
    ChildIssueContract(
        issue_number=15,
        title="LangSmith tracing + operational baseline",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
    ),
)


def child_issue_contracts() -> tuple[ChildIssueContract, ...]:
    """Return canonical v1 child issue contracts."""

    return _CHILD_ISSUE_CONTRACTS


def validate_child_issue_contracts(
    contracts: tuple[ChildIssueContract, ...] | None = None,
) -> tuple[str, ...]:
    """Validate child issue existence, epic linkage, and section contract."""

    current_contracts = contracts if contracts is not None else _CHILD_ISSUE_CONTRACTS
    errors: list[str] = []

    expected_issue_numbers = {item.issue_number for item in child_issue_plan()}
    contract_issue_numbers = {item.issue_number for item in current_contracts}

    missing_issues = sorted(expected_issue_numbers - contract_issue_numbers)
    if missing_issues:
        errors.append(f"Missing child issue contracts: {missing_issues}")

    extra_issues = sorted(contract_issue_numbers - expected_issue_numbers)
    if extra_issues:
        errors.append(f"Unexpected child issue contracts: {extra_issues}")

    expected_by_issue = {item.issue_number: item for item in child_issue_plan()}
    epic_refs = {item.epic_ref for item in current_contracts}
    if len(epic_refs) > 1:
        errors.append("All child issues must link to the same parent epic")
    if epic_refs and epic_refs != {_V1_EPIC_REF}:
        errors.append(
            f"All child issues must link to epic #{V1_EPIC_ISSUE_NUMBER} ({_V1_EPIC_REF})"
        )

    for contract in current_contracts:
        expected_issue = expected_by_issue.get(contract.issue_number)
        if expected_issue is not None and contract.title != expected_issue.title:
            errors.append(
                f"Issue #{contract.issue_number} title mismatch: "
                f"{contract.title!r} != {expected_issue.title!r}"
            )
        if contract.epic_ref != _V1_EPIC_REF:
            errors.append(
                f"Issue #{contract.issue_number} is linked to wrong epic ref: "
                f"{contract.epic_ref!r} != {_V1_EPIC_REF!r}"
            )

        missing_sections = [
            section
            for section in REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS
            if section not in contract.sections
        ]
        if missing_sections:
            errors.append(
                f"Issue #{contract.issue_number} missing required sections: {missing_sections}"
            )

    return tuple(errors)
