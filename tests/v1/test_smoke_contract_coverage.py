"""Regression guards for v1 smoke contract coverage."""

from __future__ import annotations

import ast
from pathlib import Path

SMOKE_PATH = Path("src/inv_man_intake/v1_smoke.py")
AUDIT_REPORT_PATH = Path("docs/reports/v1_smoke_contract_audit.md")
PR_DESCRIPTION_PATH = Path("docs/reports/pr-403-description.md")


def test_v1_smoke_contract_guard_accepts_current_smoke_path() -> None:
    assert smoke_contract_guard_violations(SMOKE_PATH.read_text()) == []


def test_v1_smoke_contract_guard_rejects_fixture_primary_provider() -> None:
    source = """
def run():
    return {"provider": "fixture-primary"}
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not use fixture-primary extraction providers"
    ]


def test_v1_smoke_contract_guard_rejects_dict_only_registration_shortcut() -> None:
    source = """
def run(service, path):
    return register_intake_bundle_file(path, service)
"""
    assert smoke_contract_guard_violations(source) == [
        "register_intake_bundle_file must pass core_repository and document_store"
    ]


def test_v1_smoke_contract_guard_rejects_register_intake_bundle_shortcut() -> None:
    source = """
def run(bundle, service):
    return register_intake_bundle(
        bundle,
        service,
        core_repository=object(),
    )
"""
    assert smoke_contract_guard_violations(source) == [
        "register_intake_bundle must pass core_repository and document_store"
    ]


def test_v1_smoke_contract_guard_accepts_positional_persistence_args() -> None:
    source = """
def run(bundle, service, core_repository, document_store):
    register_intake_bundle(bundle, service, core_repository, document_store)
    register_intake_bundle_file(path, service, core_repository, document_store)
"""
    assert smoke_contract_guard_violations(source) == []


def test_v1_smoke_contract_guard_accepts_mixed_persistence_args() -> None:
    source = """
def run(bundle, service, core_repository, document_store):
    register_intake_bundle(bundle, service, core_repository, document_store=document_store)
    register_intake_bundle_file(
        path,
        service,
        core_repository=core_repository,
        document_store=document_store,
    )
"""
    assert smoke_contract_guard_violations(source) == []


def test_v1_smoke_contract_guard_rejects_orphan_queue_state_module() -> None:
    source = """
from inv_man_intake.queue.state_machine import create_queue_item
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
    ]


def test_v1_smoke_contract_guard_rejects_orphan_queue_state_from_package_import() -> None:
    source = """
from inv_man_intake.queue import state_machine
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
    ]


def test_v1_smoke_contract_guard_deduplicates_repeated_violations() -> None:
    source = """
from inv_man_intake.queue.state_machine import create_queue_item
import inv_man_intake.queue.state_machine as state_machine
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
    ]


def test_v1_smoke_contract_audit_includes_row_level_trace_evidence() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    required_sections = (
        "## Verifier Disposition",
        "## Audit Scope Boundary",
        "## Contract File Inventory",
        "## Converged Follow-Up Mapping",
        "## Contract Row Matrix",
        "## Regression Gate Details",
        "## No New Follow-Up Rationale",
    )
    for section in required_sections:
        assert section in audit

    required_evidence = {
        "docs/contracts/intake_contract.md": (
            "src/inv_man_intake/v1_smoke.py:95-100",
            "tests/test_v1_acceptance_smoke.py:38-56",
        ),
        "docs/contracts/core_schema.md": (
            "src/inv_man_intake/v1_smoke.py:88",
            "tests/test_v1_acceptance_smoke.py:43-56",
        ),
        "docs/contracts/extraction_provider_contract.md": (
            "src/inv_man_intake/v1_smoke.py:244-273",
            "tests/test_v1_acceptance_smoke.py:66-70",
        ),
        "docs/contracts/extraction_thresholds.md": (
            "src/inv_man_intake/v1_smoke.py:130-156",
            "tests/test_v1_acceptance_smoke.py:70-75",
        ),
        "docs/contracts/performance_normalization.md": (
            "src/inv_man_intake/v1_smoke.py:164-178",
            "tests/test_v1_acceptance_smoke.py:78-90",
        ),
        "docs/contracts/queue_states.md": (
            "src/inv_man_intake/v1_smoke.py:186-195",
            "tests/test_v1_acceptance_smoke.py:92-100",
        ),
        "docs/contracts/queue_assignment_sla.md": (
            "src/inv_man_intake/v1_smoke.py:186-195",
            "tests/test_v1_acceptance_smoke.py:92-100",
        ),
        "docs/contracts/scoring_explainability.md": (
            "src/inv_man_intake/v1_smoke.py:202-219",
            "tests/test_v1_acceptance_smoke.py:102-109",
        ),
    }
    for contract, anchors in required_evidence.items():
        assert contract in audit
        for anchor in anchors:
            assert anchor in audit

    not_exercised_contracts = (
        "docs/contracts/core_schema_migration.md",
        "docs/contracts/provenance_history.md",
        "docs/contracts/agent-runner-output.md",
    )
    for contract in not_exercised_contracts:
        assert contract in audit
    assert "not-exercised" in audit
    assert "No issue filed from this audit" in audit


def test_v1_smoke_contract_audit_enumerates_contract_files_in_scope() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    expected_contract_files = (
        "docs/contracts/intake_contract.md",
        "docs/contracts/core_schema.md",
        "docs/contracts/extraction_provider_contract.md",
        "docs/contracts/queue_states.md",
        "docs/contracts/queue_assignment_sla.md",
        "docs/contracts/performance_normalization.md",
        "docs/contracts/scoring_explainability.md",
        "docs/contracts/extraction_thresholds.md",
        "docs/contracts/provenance_history.md",
        "docs/contracts/core_schema_migration.md",
        "docs/contracts/agent-runner-output.md",
    )
    for contract_file in expected_contract_files:
        assert contract_file in audit


def test_v1_smoke_contract_audit_has_verifier_row_matrix_depth() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    row_tokens = (
        "intake.metadata.required_fields",
        "intake.files.roles_and_source_refs",
        "core_schema.repository_hierarchy",
        "core_schema.document_store_linkage",
        "core_schema.versioned_documents",
        "core_schema_migration.apply_rollback",
        "extraction.provider_identity",
        "extraction.canonical_result_fields",
        "extraction.secondary_fallback_route",
        "extraction_thresholds.low_key_field_coverage",
        "extraction_thresholds.document_escalation",
        "performance_normalization.input_periods",
        "performance_normalization.conflict_resolution",
        "performance_normalization.benchmark_correlation",
        "queue_states.validation_queue_state",
        "queue_states.orphan_state_machine_absence",
        "queue_assignment_sla.analyst_first_assignment",
        "queue_assignment_sla.ops_reassignment",
        "queue_assignment_sla.sla_breach_scheduling",
        "scoring_explainability.final_score",
        "scoring_explainability.driver_payload",
        "provenance_history.source_location_trace",
        "provenance_history.field_corrections",
        "agent-runner-output.workflow_call_outputs",
        "smoke_trace.continuity",
    )
    for token in row_tokens:
        assert token in audit

    assert audit.count("| `") >= len(row_tokens)
    assert audit.count("No issue filed from this audit") >= 5


def test_v1_smoke_contract_audit_uses_required_disposition_labels() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    allowed = {"end-to-end", "fixture-stand-in", "not-exercised", "orphan-only"}
    matrix_section = audit.split("## Contract Row Matrix", maxsplit=1)[1].split(
        "## Regression Gate Details",
        maxsplit=1,
    )[0]
    matrix_lines = [
        line
        for line in matrix_section.splitlines()
        if line.startswith("| `") and "Contract row" not in line and " --- " not in line
    ]
    dispositions = [line.split("|")[3].strip() for line in matrix_lines]
    assert dispositions
    assert "fixture-stand-in" in dispositions
    assert "orphan-only" in dispositions
    for disposition in dispositions:
        assert disposition in allowed


def test_v1_smoke_contract_audit_rows_trace_to_smoke_or_explicit_absence() -> None:
    audit = AUDIT_REPORT_PATH.read_text()
    matrix_section = audit.split("## Contract Row Matrix", maxsplit=1)[1].split(
        "## Regression Gate Details",
        maxsplit=1,
    )[0]
    matrix_lines = [
        line
        for line in matrix_section.splitlines()
        if line.startswith("| `") and "Contract row" not in line and " --- " not in line
    ]

    for line in matrix_lines:
        columns = [column.strip() for column in line.split("|")]
        row_token = columns[1]
        disposition = columns[3]
        evidence = columns[4]

        if disposition in {"end-to-end", "fixture-stand-in"}:
            assert (
                "src/inv_man_intake/v1_smoke.py" in evidence
            ), f"{row_token} must reference the v1 smoke call site"
            assert (
                "tests/test_v1_acceptance_smoke.py" in evidence
            ), f"{row_token} must reference the v1 acceptance assertion"
        if disposition == "orphan-only":
            assert (
                "tests/v1/test_smoke_contract_coverage.py" in evidence
            ), f"{row_token} must reference the guard assertion path"
        if disposition == "not-exercised":
            assert (
                "no call site" in evidence.lower()
                or "has no" in evidence.lower()
                or "does not" in evidence.lower()
                or " not " in evidence.lower()
                or "outside the v1 smoke claim" in evidence.lower()
            ), f"{row_token} must explain non-exercised absence"


def test_pr_description_references_audit_and_followup_issues() -> None:
    description = PR_DESCRIPTION_PATH.read_text()
    assert "docs/reports/v1_smoke_contract_audit.md" in description
    assert "#379" in description
    assert "#380" in description
    assert "#381" in description
    assert "Additional per-instance follow-up issues created by this audit: none." in description


def smoke_contract_guard_violations(source: str) -> list[str]:
    violations: list[str] = []
    if "fixture-primary" in source or "fixture_primary" in source:
        violations.append("v1 smoke must not use fixture-primary extraction providers")

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if _is_orphan_queue_module(node.module):
                violations.append(
                    "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
                )
            if node.module == "inv_man_intake.queue":
                for alias in node.names:
                    if alias.name == "state_machine":
                        violations.append(
                            "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
                        )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_orphan_queue_module(alias.name):
                    violations.append(
                        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
                    )
        if isinstance(node, ast.Call) and _call_name(node.func) in {
            "register_intake_bundle",
            "register_intake_bundle_file",
        }:
            call_name = _call_name(node.func)
            missing = _missing_persistence_args(call_name, node)
            if missing:
                violations.append(f"{call_name} must pass core_repository and document_store")

    # Keep stable order while suppressing duplicate hits from multi-import variants.
    return list(dict.fromkeys(violations))


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_orphan_queue_module(module_name: str | None) -> bool:
    return bool(module_name) and module_name.startswith("inv_man_intake.queue.state_machine")


def _missing_persistence_args(call_name: str, node: ast.Call) -> set[str]:
    keywords = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
    required_positions = {
        "register_intake_bundle": {"core_repository": 3, "document_store": 4},
        "register_intake_bundle_file": {"core_repository": 3, "document_store": 4},
    }[call_name]
    return {
        name
        for name, position in required_positions.items()
        if name not in keywords and len(node.args) < position
    }
