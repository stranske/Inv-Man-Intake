# Ingestion Lifecycle Runbook (Issue #18)

## Lifecycle States

- `received`: package accepted for processing
- `processing`: parsing and storage steps in progress
- `completed`: package fully processed
- `escalated`: package requires human queue intervention

## Allowed Transitions

- `received` -> `processing`
- `received` -> `escalated`
- `processing` -> `completed`
- `processing` -> `escalated`

Terminal states:
- `completed`
- `escalated`

## Escalation Payload

Escalations include:
- package/fund/firm identifiers
- reason text
- retry flag
- fallback tool used (if any)
- file count
- event timestamp

This payload is intended for queue handoff and downstream triage.
