# Queue Audit Retention Assumptions (Issue #43)

## Goal

Keep deterministic queue-action history for override traceability without mutating prior records.

## Event Storage Assumptions

- Audit records are append-only and immutable after write.
- Events are retrieved in append order; item-level trails preserve insertion sequence.
- Each event includes actor identity (`actor_id`, `actor_role`) and timestamp (`at`).
- Override actions should include a non-empty `override_reason` when policy exceptions are used.

## Retention Baseline

- Keep queue audit events for at least 13 months to support annual compliance review windows.
- Do not delete individual events from the middle of an item trail; archive whole historical ranges only.
- If archival is required, copy complete ordered slices and verify event counts before deletion.

## Operational Notes

- In-memory repository is test-focused and models append-only semantics.
- Production persistence can map the same event schema to a durable table or log stream.
