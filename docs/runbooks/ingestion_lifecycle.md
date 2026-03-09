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
- document identifiers bound to the package
- reason text
- retry flag
- fallback tool used (if any)
- file count
- event timestamp

This payload is intended for queue handoff and downstream triage.

## Queryability

The ingestion service supports timeline queries by:
- package ID (`get_events(package_id)`)
- document ID (`get_events_by_document(document_id)`)

Record lookups are also available by:
- package ID (`get_record(package_id)`)
- document ID (`get_record_by_document(document_id)`)
