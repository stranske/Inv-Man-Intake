# Intake Contract (v1)

## Purpose

Define the canonical submission contract for inbound manager package intake.
This contract covers package metadata, file bundle metadata, and deterministic validation errors.

## Top-Level Payload

```json
{
  "metadata": { "...": "..." },
  "files": [ { "...": "..." } ]
}
```

## Metadata Fields

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `firm_name` | Yes | string | Legal or operating firm name |
| `fund_name` | Yes | string | Fund/vehicle name |
| `received_at` | Yes | string | ISO-8601 date or datetime (`2026-03-01`, `2026-03-01T09:00:00Z`) |
| `source_channel` | Yes | string | One of `email`, `portal_upload`, `data_room`, `internal_forward`, `other` |
| `submitter` | No | string | Optional sender/uploader identity |
| `external_package_id` | No | string | Optional external tracking ID |
| `contract_version` | No (recommended) | string | Contract tag understood by downstream services (default `v1` when omitted) |
| `schema_revision` | No | integer | Optional producer-side revision for non-breaking metadata additions |

## Files Entry Fields

Each entry in `files`:

| Field | Required | Type | Notes |
| --- | --- | --- | --- |
| `file_name` | Yes | string | Must include extension |
| `role` | Yes | string | Logical role (e.g., `investment_deck`, `ddq`, `performance_track_record`) |
| `source_ref` | No (recommended) | string | Ingestion trace reference (`email:msg-123`, upload ID, etc.) |
| `received_page_hint` | No | integer | Optional page hint for source trace |

## Allowed File Extensions

- Primary: `pdf`, `pptx`
- Secondary: `xlsx`, `docx`, `eml`, `txt`, `md`

Validation requires at least one primary file (`.pdf` or `.pptx`) in the bundle.

## Versioning Touchpoints

Downstream services should treat the following fields as contract/version anchors:

- `metadata.contract_version`: Canonical contract version identifier (`v1` for this document). Breaking schema changes require a new major version and a new contract document.
- `metadata.schema_revision`: Optional non-breaking producer revision marker. Consumers should ignore unknown optional metadata keys when `contract_version` is unchanged.
- `metadata.received_at`: Intake/version chronology anchor used for deterministic ordering in core schema version history.
- `metadata.external_package_id`: Stable cross-system package identity for replay/audit correlation.
- `files[*].source_ref` and `files[*].received_page_hint`: Provenance placeholders carried forward into extraction and core schema lineage fields.

Change control expectations:

- Additive optional fields may ship under `metadata.contract_version: "v1"`.
- Required field changes, semantic changes, or validation-breaking changes require a new contract major version (`v2+`) and coordinated downstream updates.
- Contract updates must land with matching tests and migration notes in downstream contracts/runbooks.

## Validation Error Schema

```json
{
  "code": "missing_required_metadata",
  "path": "metadata.fund_name",
  "message": "fund_name is required",
  "severity": "error"
}
```

Fields:
- `code`: stable machine-parseable identifier
- `path`: object path to invalid/missing field
- `message`: user-facing message
- `severity`: `error` or `warning`

## Example: Primary-Only Submission

```json
{
  "metadata": {
    "firm_name": "Atlas Partners",
    "fund_name": "Atlas Multi-Strat",
    "received_at": "2026-03-01T09:00:00Z",
    "source_channel": "email"
  },
  "files": [
    {
      "file_name": "atlas_deck.pdf",
      "role": "investment_deck",
      "source_ref": "email:message-123"
    }
  ]
}
```

## Example: Mixed Submission

```json
{
  "metadata": {
    "firm_name": "Beta Capital",
    "fund_name": "Beta Credit L/S",
    "received_at": "2026-03-01",
    "source_channel": "portal_upload",
    "submitter": "ops@betacapital.example"
  },
  "files": [
    {
      "file_name": "beta_pitch.pptx",
      "role": "investment_deck",
      "source_ref": "portal:upload-88"
    },
    {
      "file_name": "beta_returns.xlsx",
      "role": "performance_track_record",
      "source_ref": "portal:upload-89"
    },
    {
      "file_name": "beta_ddq.docx",
      "role": "ddq",
      "source_ref": "portal:upload-90"
    }
  ]
}
```
