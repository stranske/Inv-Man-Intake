# Core Schema Migration (Issue #28)

## Scope

This migration introduces the foundational relational hierarchy for v1:
- `firms`
- `funds`
- `documents`

## Relationship Rules

- `funds.firm_id` -> `firms.firm_id` (foreign key, `ON DELETE CASCADE`)
- `documents.fund_id` -> `funds.fund_id` (foreign key, `ON DELETE CASCADE`)

## Constraints

- Every table uses a text primary key (`firm_id`, `fund_id`, `document_id`).
- Required identifier/name fields are guarded with non-blank `CHECK (length(trim(...)) > 0)` constraints.
- Documents include date/version fields (`received_at`, `version_date`) to support version history.
- Document uniqueness across versions uses `(fund_id, file_hash, version_date)`.

## Indexes

- `idx_funds_firm_id`
- `idx_documents_fund_id`
- `idx_documents_received_at`

These indexes target the primary lookup paths for hierarchy traversal and date-based scans.

## Rollback Assumptions

Rollback is SQLite-specific and intentionally disables FK enforcement before drops:
- `PRAGMA foreign_keys = OFF`

Then it drops tables in reverse dependency order:
1. `documents`
2. `funds`
3. `firms`

Finally, rollback restores FK enforcement:
- `PRAGMA foreign_keys = ON`

Rollback is intended for test/dev environments or controlled migration reversal events.

## Files

- Up migration:
  - `src/inv_man_intake/data/migrations/sql/0001_core_firm_fund_document.up.sql`
- Down migration:
  - `src/inv_man_intake/data/migrations/sql/0001_core_firm_fund_document.down.sql`
- Migration runner:
  - `src/inv_man_intake/data/migrations/core_schema.py`
- Tests:
  - `tests/data/test_migration_core_schema.py`
