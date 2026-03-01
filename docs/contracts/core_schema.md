# Core Schema Contract (v1)

## Entity Hierarchy

The canonical hierarchy is:
1. `firm`
2. `fund`
3. `document`

## Repository API

`CoreRepository` exposes:
- `ensure_core_schema()`
- `create_firm()`, `get_firm()`, `update_firm_aliases()`
- `create_fund()`, `get_fund()`
- `create_document()`, `get_document()`
- `list_document_versions(fund_id, file_name)`
- `list_provenance_rows(document_id)`

## Core Tables

### `firms`
- `firm_id` (PK)
- `legal_name`
- `aliases_json`
- `created_at`

### `funds`
- `fund_id` (PK)
- `firm_id` (FK -> `firms.firm_id`)
- `fund_name`
- `strategy`
- `asset_class`
- `created_at`

### `documents`
- `document_id` (PK)
- `fund_id` (FK -> `funds.fund_id`)
- `file_name`
- `file_hash`
- `received_at`
- `version_date`
- `source_channel`
- `created_at`

## Version Lookup

`list_document_versions` returns ordered versions for one `(fund_id, file_name)` pair by:
1. `version_date`
2. `received_at`

This creates deterministic ordering for downstream processing.

## Provenance Lookup Behavior

`list_provenance_rows(document_id)`:
- Returns `()` when `extracted_fields` table is absent.
- Returns ordered `(field_key, value, source_page)` rows when present.

This allows repository code to remain forward-compatible while provenance tables are rolled out incrementally.
