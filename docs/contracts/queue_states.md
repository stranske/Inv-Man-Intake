# Queue State Machine Contract

Issue: #40  
Parent workstream: #14

This document defines the validation queue state semantics, transition matrix, and
permission checks for deterministic queue behavior.

## States

- `new`: Newly created queue item, not yet assigned.
- `assigned`: Item has an assignee and is waiting for active review.
- `in_review`: Assignee is actively validating and resolving the item.
- `blocked`: Item cannot progress without an external dependency or ops decision.
- `resolved`: Terminal state; item processing is complete.

## Allowed Transitions

| From | To |
| --- | --- |
| `new` | `assigned` |
| `assigned` | `in_review`, `blocked` |
| `in_review` | `resolved`, `blocked`, `assigned` |
| `blocked` | `assigned`, `in_review` |
| `resolved` | _none_ |

Any transition outside this matrix is rejected with:

- `QueueTransitionError("invalid transition: <from> -> <to>")`

## Permission Rules

### Assignment

- `new -> assigned` via `assign_item`:
  - Allowed actor roles: `analyst`, `ops`
  - Rejected for `system` with:
    - `QueuePermissionError("only analyst or ops can assign new items")`
- Reassignment from `assigned`/`in_review`/`blocked` via `assign_item`:
  - Allowed actor role: `ops` only
  - Rejected otherwise with:
    - `QueuePermissionError("only ops can reassign active items")`
- Assignment from `resolved` rejected with:
  - `QueueTransitionError("cannot assign item from terminal state: resolved")`

### State Transitions

- Transition to `assigned` is allowed only for `ops`:
  - Rejected otherwise with:
    - `QueuePermissionError("only ops can transition item to assigned")`
- Transition to `in_review`, `blocked`, or `resolved`:
  - Allowed for assignee
  - Allowed for `ops`
  - Rejected for non-assignee analyst/system actors with:
    - `QueuePermissionError("only assignee or ops can transition this item")`

## Deterministic Behavior

- `transition_item(..., to_state=<current_state>)` is a no-op and returns the input item.
- `actor_id` and assignment IDs must be non-empty.
- All item timestamps are persisted in UTC ISO-8601 format with second precision.
