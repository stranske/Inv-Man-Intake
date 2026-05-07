# Validation Queue State Contract

Canonical source of truth for the v1 validation queue state machine. The
implementation lives in `src/inv_man_intake/workflow_validation.py`; the
dashboard query layer in `src/inv_man_intake/validation_queue_api.py` and the
extraction escalation router in `src/inv_man_intake/extraction/orchestrator.py`
must agree with the names below.

History: an earlier `new -> assigned -> in_review -> blocked -> resolved`
contract (and an orphan `src/inv_man_intake/queue/state_machine.py`) was
removed when issue #381 reconciled docs with the integrated path. There is no
backwards-compatible alias for those names.

## States

- `pending_triage`: Newly created queue item with no analyst owner.
- `in_validation`: An analyst (or ops) has claimed the item and is actively
  validating extracted fields.
- `awaiting_manager_response`: The analyst has paused validation pending a
  clarification from the manager.
- `ops_review`: The item has been escalated for an ops policy decision.
- `completed`: Terminal state; validation succeeded and the item is closed.
- `rejected`: Terminal state; validation rejected the package.

## Allowed Transitions

| From                          | To                                                          |
| ----------------------------- | ----------------------------------------------------------- |
| `pending_triage`              | `in_validation`                                             |
| `in_validation`               | `awaiting_manager_response`, `ops_review`, `completed`, `rejected` |
| `awaiting_manager_response`   | `in_validation`, `ops_review`, `rejected`                   |
| `ops_review`                  | `in_validation`, `completed`, `rejected`                    |
| `completed`                   | _none_ (terminal)                                           |
| `rejected`                    | _none_ (terminal)                                           |

`transition_state(..., to_state=<current_state>)` is a no-op and returns the
input item unchanged. Any other transition outside this matrix is rejected
with:

- `ValidationWorkflowError("Invalid transition: <from> -> <to>")`

## Ownership and Permissions

- `pending_triage -> in_validation` happens via `claim_for_analyst_triage`.
  The item must be unowned (`owner_id is None`); the call sets
  `owner_role="analyst"` and records a `claim` event.
- Already-claimed items reject re-claim with
  `ValidationWorkflowError("Queue item already has an owner")`.
- `transfer_owner` swaps ownership between analysts and ops:
  - The item must not be terminal (`completed`/`rejected`).
  - The actor must be the current owner OR have `actor_role="ops"`.
  - Rejected otherwise with
    `ValidationWorkflowError("Only current owner or ops can transfer ownership")`.
- `transition_state` requires the item to be claimed; callers must be the
  current owner or have `actor_role="ops"`. Rejected otherwise with
  `ValidationWorkflowError("Only current owner or ops can transition state")`.

See `docs/contracts/queue_assignment_sla.md` for analyst-first ownership and
SLA timing rules; that contract layers on top of these states.

## Escalation Routes

`src/inv_man_intake/extraction/orchestrator.py` emits one of two escalation
routes when extraction fails to converge:

- A single failed provider routes to `pending_triage` (analyst will claim).
- Multiple distinct failed providers route to `ops_review` (skip analyst
  triage and request an ops policy decision).

Both route names are members of this state set; downstream consumers can map
the escalation route directly to a queue item state without translation.

## Public Imports

The single public entry point for queue items is
`inv_man_intake.workflow_validation`. The `inv_man_intake.queue` package
exposes assignment/SLA helpers but no longer re-exports a separate state
machine or a duplicate `create_queue_item`; importers must use:

```python
from inv_man_intake.workflow_validation import (
    create_queue_item,
    claim_for_analyst_triage,
    transfer_owner,
    transition_state,
    to_queue_row,
    ValidationQueueItem,
    ValidationQueueRow,
    ValidationState,
    ValidationWorkflowError,
)
```

## Determinism

- `item_id`, `package_id`, `escalation_reason`, `actor_id`, `analyst_id`,
  `new_owner_id`, and `owner_id` must all be non-empty; `create_queue_item`,
  `claim_for_analyst_triage`, `transfer_owner`, and `transition_state` raise
  `ValidationWorkflowError` if any required identifier is empty.
- All item timestamps are persisted in UTC ISO-8601 format with second
  precision (see `_utc_now` in `workflow_validation.py`).
- `claim_for_analyst_triage`, `transfer_owner`, and `transition_state`
  append exactly one immutable `QueueEvent` to `item.events` per applied
  change. `transition_state(..., to_state=<current_state>)` is a no-op,
  returns the input unchanged, and appends no event.

## Smoke Coverage

`tests/queue/test_v1_smoke_state_transition.py` drives a real
`pending_triage -> in_validation -> completed` transition path tied to the
v1 conflict/escalation flow (`tests/test_v1_acceptance_smoke.py`'s queue
assignment item id) and parses this file's `## States` bullet list to
assert that documented state names match `ValidationState` in
`workflow_validation.py`. Doc/code drift on either the canonical state set
or the integrated transition path therefore fails CI before merge.
