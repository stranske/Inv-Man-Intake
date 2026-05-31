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

## Persisting Real Document Bytes

By default the persistence path resolves content with `deterministic_fixture_content`,
which synthesizes placeholder bytes (`{package_id}\n{file_name}\n{source_ref}\n`). That
keeps fixture tests deterministic, but the persisted `file_hash`/`byte_size` then
describe the placeholder text rather than the real document.

To anchor provenance to the real bytes, pass `filesystem_content_resolver(base_dir)` as
the `content_resolver`. It maps each bundle entry's `file_name` to `base_dir / file_name`
and stores the file's actual bytes, so `DocumentVersionRecord.file_hash` equals the
SHA-256 of the on-disk document. It never falls back to fabricated content: a missing or
unreadable source file raises `FileNotFoundError` so the gap is surfaced, not masked.

```python
from pathlib import Path

from inv_man_intake.intake.integration import (
    filesystem_content_resolver,
    register_intake_bundle,
)
from inv_man_intake.intake.service import IngestionService

result = register_intake_bundle(
    bundle,  # every entry's file_name must resolve under the base directory
    IngestionService(),
    core_repository=core_repository,
    document_store=document_store,
    content_resolver=filesystem_content_resolver(Path("tests/fixtures/extraction")),
)
# result.persisted_documents[i].file_hash == sha256(real file bytes)
```

The resolver is deterministic and in-perimeter: it only reads local files and does not
fetch from email/drop-folder connectors or any remote source. Pair it with the durable
filesystem document store (`register_intake_bundle_to_path` / `FilesystemDocumentStore`)
so the real bytes are retained across processes; with the in-memory store the persisted
hashes are correct but ephemeral.
