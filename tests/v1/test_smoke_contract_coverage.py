"""Regression guards for v1 smoke contract coverage."""

from __future__ import annotations

import ast
from pathlib import Path

SMOKE_PATH = Path("src/inv_man_intake/v1_smoke.py")


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


def test_v1_smoke_contract_guard_rejects_orphan_queue_state_module() -> None:
    source = """
from inv_man_intake.queue.state_machine import create_queue_item
"""
    assert smoke_contract_guard_violations(source) == [
        "v1 smoke must not import discarded inv_man_intake.queue.state_machine"
    ]


def smoke_contract_guard_violations(source: str) -> list[str]:
    violations: list[str] = []
    if "fixture-primary" in source or "fixture_primary" in source:
        violations.append("v1 smoke must not use fixture-primary extraction providers")

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "inv_man_intake.queue.state_machine":
            violations.append("v1 smoke must not import discarded inv_man_intake.queue.state_machine")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "inv_man_intake.queue.state_machine":
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

    return violations


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""
