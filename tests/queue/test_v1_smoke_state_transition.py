"""Smoke-linked transition test for the v1 validation queue contract.

Drives a real ``pending_triage -> in_validation -> completed`` transition for
the v1 conflict/escalation queue item from
``tests/test_v1_acceptance_smoke.py``, and parses
``docs/contracts/queue_states.md`` to assert that the state names documented
there match ``ValidationState``. Doc/code drift therefore fails CI.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest

from inv_man_intake.workflow_validation import (
    ValidationState,
    ValidationWorkflowError,
    claim_for_analyst_triage,
    create_queue_item,
    transition_state,
)

_CONTRACT_PATH = Path("docs/contracts/queue_states.md")
_STATE_BULLET_RE = re.compile(r"^- `([a-z_]+)`:", re.MULTILINE)


def test_documented_state_names_match_validation_state() -> None:
    contract_text = _CONTRACT_PATH.read_text(encoding="utf-8")
    states_section = contract_text.split("## States", 1)[1].split("##", 1)[0]
    documented = set(_STATE_BULLET_RE.findall(states_section))
    assert documented == set(get_args(ValidationState)), (
        "docs/contracts/queue_states.md state list disagrees with "
        "ValidationState in workflow_validation.py"
    )


def test_v1_smoke_queue_item_drives_documented_state_path(v1_smoke_artifacts) -> None:
    artifacts = v1_smoke_artifacts

    item = create_queue_item(
        item_id=artifacts.queue_assignment.item_id,
        package_id=artifacts.record.package_id,
        escalation_reason="performance_conflict",
    )
    assert item.state == "pending_triage"

    claimed = claim_for_analyst_triage(item, analyst_id=artifacts.queue_assignment.owner_id)
    assert claimed.state == "in_validation"

    completed = transition_state(
        claimed,
        actor_id=artifacts.queue_assignment.owner_id,
        actor_role="analyst",
        to_state="completed",
    )
    assert completed.state == "completed"
    assert [event.action for event in completed.events] == ["claim", "state_transition"]


def test_v1_smoke_queue_rejects_legacy_state_names() -> None:
    item = create_queue_item(
        item_id="pkg_pdf_mixed_001:validation:performance_conflict",
        package_id="pkg_pdf_mixed_001",
        escalation_reason="performance_conflict",
    )
    claimed = claim_for_analyst_triage(item, analyst_id="analyst_001")

    with pytest.raises(ValidationWorkflowError, match="Invalid transition"):
        transition_state(
            claimed,
            actor_id="analyst_001",
            actor_role="analyst",
            to_state="resolved",  # type: ignore[arg-type]
        )
