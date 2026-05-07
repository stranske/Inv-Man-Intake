"""Contract test: docs/contracts/queue_states.md state names and transitions match the implementation.

If this file passes but the doc and code disagree, one of these parsers is broken.
If the doc or code changes without updating the other, this file will fail CI.
"""

from __future__ import annotations

import dataclasses
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

_QUEUE_STATES_DOC = Path("docs/contracts/queue_states.md")
_BACKTICK_RE = re.compile(r"`([^`]+)`")


def _read_doc() -> str:
    text = _QUEUE_STATES_DOC.read_text()
    assert text, f"{_QUEUE_STATES_DOC} is empty"
    return text


def _section_text(text: str, heading: str) -> str:
    """Return text from `heading` to the next ## heading."""
    pattern = re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise AssertionError(f"Section '{heading}' not found in queue_states.md")
    start = match.end()
    next_sec = text.find("\n## ", start)
    return text[start:next_sec] if next_sec != -1 else text[start:]


def _parse_documented_states(text: str) -> frozenset[str]:
    section = _section_text(text, "## States")
    names = re.findall(r"^- `(\w+)`:", section, re.MULTILINE)
    if not names:
        raise AssertionError("No state names found in ## States section of queue_states.md")
    return frozenset(names)


def _parse_documented_transitions(text: str) -> dict[str, frozenset[str]]:
    """Parse the Allowed Transitions table into {from_state: {to_state, ...}}."""
    section = _section_text(text, "## Allowed Transitions")
    result: dict[str, frozenset[str]] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) < 2:
            continue
        from_names = _BACKTICK_RE.findall(cells[0])
        if not from_names:
            continue  # header or separator row
        to_names = _BACKTICK_RE.findall(cells[1])
        result[from_names[0]] = frozenset(to_names)
    return result


def test_documented_states_match_validation_state_literal() -> None:
    """docs/contracts/queue_states.md state names must exactly match ValidationState."""
    text = _read_doc()
    documented = _parse_documented_states(text)
    implemented = frozenset(get_args(ValidationState))

    extra_in_docs = documented - implemented
    extra_in_code = implemented - documented

    assert (
        not extra_in_docs
    ), f"States listed in docs/contracts/queue_states.md but absent from ValidationState: {extra_in_docs}"
    assert (
        not extra_in_code
    ), f"States in ValidationState but absent from docs/contracts/queue_states.md: {extra_in_code}"


def test_transition_matrix_matches_documentation() -> None:
    """Every allowed and blocked transition must exactly match docs/contracts/queue_states.md."""
    text = _read_doc()
    documented = _parse_documented_transitions(text)

    # Sanity: every documented from-state must be a known ValidationState
    known = frozenset(get_args(ValidationState))
    unknown_from = frozenset(documented) - known
    assert not unknown_from, f"Documented from-states not in ValidationState: {unknown_from}"

    # Build a claimed item we can patch into any from_state via dataclasses.replace
    base = create_queue_item(
        item_id="contract-matrix-1",
        package_id="pkg-contract-matrix",
        escalation_reason="contract_test",
    )
    claimed = claim_for_analyst_triage(base, analyst_id="analyst-contract")

    for from_state in get_args(ValidationState):
        allowed_to = documented.get(from_state, frozenset())
        item_in_state = dataclasses.replace(claimed, state=from_state)

        for to_state in get_args(ValidationState):
            if from_state == to_state:
                continue  # same-state no-ops are always allowed

            if to_state in allowed_to:
                # Documented as allowed — must succeed
                try:
                    transition_state(
                        item_in_state,
                        actor_id="analyst-contract",
                        actor_role="analyst",
                        to_state=to_state,
                    )
                except ValidationWorkflowError as exc:
                    raise AssertionError(
                        f"Documented valid transition {from_state!r} -> {to_state!r} was rejected: {exc}"
                    ) from exc
            else:
                # Not in the documented allowed set — must raise ValidationWorkflowError
                with pytest.raises(
                    ValidationWorkflowError,
                    match="Invalid transition",
                ):
                    transition_state(
                        item_in_state,
                        actor_id="analyst-contract",
                        actor_role="analyst",
                        to_state=to_state,
                    )
