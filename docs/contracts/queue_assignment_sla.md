# Queue Assignment + SLA Contract

Issue: #41  
Parent workstream: #14

This document defines analyst-first queue ownership behavior and same-day SLA fields.

## Analyst-First Assignment Policy

- New queue records default to analyst ownership.
- `create_analyst_first_assignment` sets:
  - `owner_role=analyst`
  - `owner_id=<analyst_id>`
  - initial audit event `assigned_analyst`

## Ops Reassignment Flow

- Analysts can explicitly reassign to ops when operational blockers are found.
- `reassign_to_ops_for_block` requires:
  - record currently analyst-owned
  - caller is the current analyst owner
  - non-empty ops target and reason
- Reassignment appends immutable event `reassigned_to_ops` with blocker note.

## SLA Fields

- `created_at`: queue item creation timestamp.
- `assigned_at`: timestamp when current owner assignment took effect.
- `due_at`: same-day target (`23:59:59` in the assignment timestamp timezone).
- `breached_at`: set only once when `now > due_at`.

## Deterministic Breach Logic

- Breach check runs via `update_sla_breach`/`mark_breach_if_due`.
- If current time is on or before `due_at`, breach remains unset.
- If current time is after `due_at`, `breached_at` is set to that observed time.
- All SLA datetimes must be timezone-aware.
