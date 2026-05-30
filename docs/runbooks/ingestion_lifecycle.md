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

## Durable On-Disk Intake

Use `register_intake_bundle_to_path(...)` when an intake run must survive process exit.
It opens an on-disk SQLite core repository and a filesystem document store, then routes
the bundle through the same deterministic `register_intake_bundle_file(...)` path.

```bash
python - <<'PY'
from pathlib import Path

from inv_man_intake.intake.integration import register_intake_bundle_to_path

result = register_intake_bundle_to_path(
    Path("tests/fixtures/intake/pdf_primary_mixed_bundle.json"),
    db_path=Path("runs/intake/core.sqlite"),
    store_root=Path("runs/intake/document-store"),
)
print(result.accepted, result.package_id, len(result.persisted_documents))
PY
```

The command is local-only: it writes SQLite rows plus document blobs/metadata under
`runs/intake/` and does not call external services.
