"""Tests that docs/INV_MAN_INTAKE_PLAN_V1.md Section 6 is structurally complete.

These tests pin the four required elements of the Dependency Graph section so
a future edit that accidentally drops a sub-section is caught in CI.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PLAN_PATH = Path("docs/INV_MAN_INTAKE_PLAN_V1.md")
_CHILD_ISSUE_NUMBERS = tuple(range(8, 16))


@pytest.fixture(scope="module")
def plan_text() -> str:
    return _PLAN_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def section6_text(plan_text: str) -> str:
    """Extract the text of Section 6 (stops at the next ## heading)."""
    match = re.search(r"^## 6\).*?(?=^## |\Z)", plan_text, re.MULTILINE | re.DOTALL)
    assert match is not None, "Section '## 6)' not found in plan doc"
    return match.group(0)


# --- Task 1: issue-to-workstream map ---

def test_section6_exists(section6_text: str) -> None:
    assert "Dependency Graph" in section6_text or "Execution Order" in section6_text


def test_issue_to_workstream_table_covers_all_child_issues(section6_text: str) -> None:
    for issue_number in _CHILD_ISSUE_NUMBERS:
        assert f"#{issue_number}" in section6_text, (
            f"Issue #{issue_number} missing from Section 6"
        )


def test_issue_to_workstream_table_includes_milestone_column(section6_text: str) -> None:
    assert "Milestone" in section6_text


# --- Task 2: blocking relationships (Mermaid + plain text) ---

def test_blocking_relationships_mermaid_block_present(section6_text: str) -> None:
    assert "```mermaid" in section6_text, "Mermaid diagram block missing from Section 6"


def test_blocking_relationships_plain_text_present(section6_text: str) -> None:
    assert "blocks" in section6_text, "Plain-text edge list missing from Section 6"


# --- Task 3: recommended execution order ---

def test_recommended_execution_order_present(section6_text: str) -> None:
    assert "execution order" in section6_text.lower() or "critical path" in section6_text.lower()


def test_milestone_waves_described(section6_text: str) -> None:
    for wave in ("Milestone A", "Milestone B", "Milestone C", "Milestone D"):
        assert wave in section6_text, f"{wave} wave missing from execution order description"


# --- Task 4: parallelization gates ---

def test_parallelization_gates_section_present(section6_text: str) -> None:
    assert "parallelization" in section6_text.lower() or "gates" in section6_text.lower()


def test_parallelization_gates_reference_waves(section6_text: str) -> None:
    assert "A wave" in section6_text or "wave" in section6_text.lower()
