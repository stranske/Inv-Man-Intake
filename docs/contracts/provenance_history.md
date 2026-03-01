# Field Provenance and Correction History Schema

## Purpose

Track extracted field values with source-document provenance and preserve an append-only correction history.

## Tables

### `extracted_fields`

Stores machine-extracted values and provenance pointers:
- `field_id` (PK)
- `document_id` (FK -> `documents.document_id`)
- `field_key`
- `value`
- `confidence`
- `source_page`
- `source_snippet`
- `extracted_at`

### `field_corrections`

Stores human or system corrections over time:
- `correction_id` (PK, autoincrement)
- `field_id` (FK -> `extracted_fields.field_id`)
- `corrected_value`
- `reason`
- `corrected_by`
- `corrected_at`

## Append-Only Rule

Corrections are never in-place updates to `extracted_fields.value`.
Each correction inserts a new row in `field_corrections`.
The latest effective value is determined by the newest correction timestamp (and correction ID tie-breaker).

## Key Access Patterns

- Fetch latest value for field: prefer newest correction, fallback to original extracted value.
- Fetch full correction history: ordered by insertion (`correction_id ASC`).
