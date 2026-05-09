"""Regression guards for v1 smoke contract coverage."""

from __future__ import annotations

import ast
from pathlib import Path

SMOKE_PATH = Path("src/inv_man_intake/v1_smoke.py")
AUDIT_REPORT_PATH = Path("docs/reports/v1_smoke_contract_audit.md")


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
    required_evidence = {
        "docs/contracts/intake_contract.md": (
            "src/inv_man_intake/v1_smoke.py:94-99",
            "tests/test_v1_acceptance_smoke.py:37-55",
        ),
        "docs/contracts/core_schema.md": (
            "src/inv_man_intake/v1_smoke.py:87",
            "tests/test_v1_acceptance_smoke.py:42-55",
        ),
        "docs/contracts/extraction_provider_contract.md": (
            "src/inv_man_intake/v1_smoke.py:228-257",
            "tests/test_v1_acceptance_smoke.py:67-69",
        ),
        "docs/contracts/extraction_thresholds.md": (
            "src/inv_man_intake/v1_smoke.py:129-150",
            "tests/test_v1_acceptance_smoke.py:70-75",
        ),
        "docs/contracts/performance_normalization.md": (
            "src/inv_man_intake/v1_smoke.py:163-172",
            "tests/test_v1_acceptance_smoke.py:81-89",
        ),
        "docs/contracts/queue_states.md": (
            "src/inv_man_intake/v1_smoke.py:174-178",
            "tests/test_v1_acceptance_smoke.py:91-99",
        ),
        "docs/contracts/queue_assignment_sla.md": (
            "src/inv_man_intake/v1_smoke.py:174-178",
            "tests/test_v1_acceptance_smoke.py:91-99",
        ),
        "docs/contracts/scoring_explainability.md": (
            "src/inv_man_intake/v1_smoke.py:191-203",
            "tests/test_v1_acceptance_smoke.py:104-108",
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
            keywords = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
            missing = {"core_repository", "document_store"} - keywords
            if missing:
                violations.append(
                    f"{_call_name(node.func)} must pass core_repository and document_store"
                )

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
