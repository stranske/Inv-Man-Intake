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
    scope_boundaries: tuple[str, ...] = ()
    non_goals: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()


_V1_EPIC_REF = "v1-single-execution-container"
V1_EPIC_ISSUE_NUMBER = 7


_CHILD_ISSUE_CONTRACTS: tuple[ChildIssueContract, ...] = (
    ChildIssueContract(
        issue_number=8,
        title="Intake and document registry",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
        scope_boundaries=(
            "Ingest PDF, PPTX, XLSX, DOCX, and email-note packages.",
            "Persist document version metadata using hash and received-date fields.",
            "Record document-level provenance pointers for downstream extraction.",
        ),
        non_goals=(
            "No scoring, ranking, or asset-class weighting logic.",
            "No external enrichment providers.",
        ),
        tasks=(
            "Implement package intake schema validation for supported file types.",
            "Add document registry persistence for version hash and received timestamp.",
            "Write unit tests covering ingestion success and unsupported-format rejection.",
        ),
        acceptance_criteria=(
            "Running ingestion tests confirms only supported file types are accepted.",
            "Registry records expose deterministic hash and received-date values per document.",
        ),
    ),
    ChildIssueContract(
        issue_number=9,
        title="Extraction confidence + fallback routing",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
        scope_boundaries=(
            "Apply field-level and document-level confidence thresholds during extraction.",
            "Route low-confidence or failed extraction attempts to fallback and escalation paths.",
            "Capture retry attempt outcomes for operational review.",
        ),
        non_goals=(
            "No image usefulness ranking logic.",
            "No analyst queue ownership workflows.",
        ),
        tasks=(
            "Implement confidence policy evaluation using approved threshold bands.",
            "Add fallback retry orchestration before escalation routing.",
            "Write tests for auto-accept, retry, and escalation outcomes.",
        ),
        acceptance_criteria=(
            "Tests verify records below configured confidence thresholds are routed to escalation.",
            "Tests verify extraction retries occur before final fallback escalation.",
        ),
    ),
    ChildIssueContract(
        issue_number=10,
        title="Image intelligence + user feedback loop",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
        scope_boundaries=(
            "Classify extracted images as informative or boilerplate.",
            "Capture analyst feedback events on image usefulness.",
            "Persist feedback records for iterative model updates.",
        ),
        non_goals=(
            "No final asset-class score computation.",
            "No workflow state ownership transitions.",
        ),
        tasks=(
            "Implement image classification labels for informative versus boilerplate artifacts.",
            "Add feedback event schema for usefulness and quality ranking submissions.",
            "Write tests validating feedback persistence and retrieval.",
        ),
        acceptance_criteria=(
            "Tests verify each processed image receives a deterministic classification label.",
            "Tests verify feedback submissions are stored with timestamped event metadata.",
        ),
    ),
    ChildIssueContract(
        issue_number=11,
        title="Core schema and storage contracts",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
        scope_boundaries=(
            "Define firm, fund, and document relational schema primitives.",
            "Document storage contracts required by ingestion and extraction layers.",
            "Persist field-level provenance pointers in schema definitions.",
        ),
        non_goals=(
            "No confidence threshold routing logic.",
            "No queue state machine implementation.",
        ),
        tasks=(
            "Implement initial core schema migration for firm, fund, and document entities.",
            "Add contract documentation for repository and storage-layer interfaces.",
            "Write migration tests verifying required tables and provenance columns.",
        ),
        acceptance_criteria=(
            "Migration tests confirm firm, fund, and document tables are created successfully.",
            "Tests verify contract docs define required provenance and versioning storage fields.",
        ),
    ),
    ChildIssueContract(
        issue_number=12,
        title="Performance normalization + conflict rules",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
        scope_boundaries=(
            "Normalize monthly, quarterly, and annual performance data inputs.",
            "Enforce Excel-preferred conflict resolution with escalation above 5 percent deltas.",
            "Compute prioritized risk and return metrics from normalized series.",
        ),
        non_goals=(
            "No UI queue ownership assignment controls.",
            "No LangSmith tracing framework setup.",
        ),
        tasks=(
            "Implement performance normalization pipeline across supported frequency cadences.",
            "Add conflict-resolution policy that prefers Excel records before escalation.",
            "Write tests for monthly-required validation and greater-than-5-percent conflicts.",
        ),
        acceptance_criteria=(
            "Tests verify missing monthly returns block auto-pass normalization paths.",
            "Tests verify conflicts above five percent trigger escalation events.",
        ),
    ),
    ChildIssueContract(
        issue_number=13,
        title="Asset-class scoring + explainability output",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
        scope_boundaries=(
            "Apply asset-class-specific weighting sets to normalized inputs.",
            "Generate explainable score component outputs for analyst trust.",
            "Publish queue-ready scoring summaries for downstream triage.",
        ),
        non_goals=(
            "No ingestion-format parsing implementation.",
            "No extraction retry policy updates.",
        ),
        tasks=(
            "Implement asset-class weighting configuration and score aggregation logic.",
            "Add explainability renderer for component-level contribution output.",
            "Write tests validating score determinism and explanation payload completeness.",
        ),
        acceptance_criteria=(
            "Tests verify each supported asset class returns a deterministic weighted score.",
            "Tests verify explainability output includes all component contributions and totals.",
        ),
    ),
    ChildIssueContract(
        issue_number=14,
        title="Validation queue ownership + workflow states",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
        scope_boundaries=(
            "Implement analyst-first queue ownership assignment.",
            "Define workflow states for triage, in-review, and resolved transitions.",
            "Persist ownership and state-change audit details.",
        ),
        non_goals=(
            "No external enrichment integrations.",
            "No performance metric normalization engine changes.",
        ),
        tasks=(
            "Implement workflow state transition validation for queue items.",
            "Add analyst ownership assignment logic for new escalated records.",
            "Write tests for valid transitions and invalid transition rejection.",
        ),
        acceptance_criteria=(
            "Tests verify escalated items default to analyst-first ownership assignments.",
            "Tests verify invalid state transitions are rejected with explicit errors.",
        ),
    ),
    ChildIssueContract(
        issue_number=15,
        title="LangSmith tracing + operational baseline",
        epic_ref=_V1_EPIC_REF,
        sections=REQUIRED_AGENT_ISSUE_FORMAT_SECTIONS,
        scope_boundaries=(
            "Enable tracing hooks across ingestion, extraction, and scoring boundaries.",
            "Document operational baseline checks aligned with current CI gates.",
            "Validate tracing configuration and fallback behavior when disabled.",
        ),
        non_goals=(
            "No new mandatory CI gates beyond current defaults.",
            "No asset-class scoring policy adjustments.",
        ),
        tasks=(
            "Implement tracing context propagation helpers across core pipeline stages.",
            "Add setup validation for required tracing environment configuration.",
            "Write tests for tracing enablement and disabled fallback paths.",
        ),
        acceptance_criteria=(
            "Tests verify tracing spans are emitted for configured pipeline stages.",
            "Tests verify pipeline execution continues when tracing is disabled.",
        ),
    ),
)


_ACTIONABLE_TASK_VERBS = {
    "add",
    "apply",
    "build",
    "capture",
    "compute",
    "define",
    "document",
    "enforce",
    "enable",
    "generate",
    "implement",
    "persist",
    "publish",
    "record",
    "route",
    "validate",
    "wire",
    "write",
}
_TESTABLE_CRITERION_SIGNALS = {
    "test",
    "tests",
    "verify",
    "confirms",
    "running",
    "returns",
    "records",
    "trigger",
    "created",
}


def _is_actionable_task(task: str) -> bool:
    words = task.strip().split()
    if len(words) < 4:
        return False
    return words[0].lower() in _ACTIONABLE_TASK_VERBS


def _is_testable_criterion(criterion: str) -> bool:
    lowered = criterion.lower()
    return any(signal in lowered for signal in _TESTABLE_CRITERION_SIGNALS)


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

        if not contract.scope_boundaries:
            errors.append(f"Issue #{contract.issue_number} must define explicit scope boundaries")
        if not contract.non_goals:
            errors.append(f"Issue #{contract.issue_number} must define explicit non-goals")

        if len(contract.tasks) < 2:
            errors.append(
                f"Issue #{contract.issue_number} must define at least two actionable tasks"
            )
        else:
            non_actionable_tasks = [
                task for task in contract.tasks if not _is_actionable_task(task)
            ]
            if non_actionable_tasks:
                errors.append(
                    f"Issue #{contract.issue_number} has non-actionable tasks: "
                    f"{non_actionable_tasks}"
                )

        if len(contract.acceptance_criteria) < 2:
            errors.append(
                f"Issue #{contract.issue_number} must define at least two testable acceptance criteria"
            )
        else:
            non_testable_criteria = [
                criterion
                for criterion in contract.acceptance_criteria
                if not _is_testable_criterion(criterion)
            ]
            if non_testable_criteria:
                errors.append(
                    f"Issue #{contract.issue_number} has non-testable acceptance criteria: "
                    f"{non_testable_criteria}"
                )

    return tuple(errors)
