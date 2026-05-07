"""Smoke-linked transition test for the v1 validation queue contract.

Locks `docs/contracts/queue_states.md` against the integrated workflow path:
the v1 conflict/escalation queue item must move
`pending_triage -> in_validation -> completed`, and only the documented
state names are allowed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.v1_smoke import run_v1_smoke_pipeline
from inv_man_intake.workflow_validation import (
    ValidationWorkflowError,
    claim_for_analyst_triage,
    create_queue_item,
    transition_state,
)

_FIXTURE_ROOT = Path("tests/fixtures/intake")
_SMOKE_PACKAGE_ID = "pkg_pdf_mixed_001"
_EXPECTED_DOCUMENT_IDS = (
    "pkg_pdf_mixed_001:doc:0",
    "pkg_pdf_mixed_001:doc:1",
    "pkg_pdf_mixed_001:doc:2",
    "pkg_pdf_mixed_001:doc:3",
)


def test_v1_smoke_queue_item_drives_documented_state_path() -> None:
    artifacts = run_v1_smoke_pipeline(
        fixture_root=_FIXTURE_ROOT,
        package_id=_SMOKE_PACKAGE_ID,
        expected_document_ids=_EXPECTED_DOCUMENT_IDS,
    )

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
