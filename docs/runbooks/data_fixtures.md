# Data Fixture Runbook

This runbook documents the repeatable fixture workflow for schema integrity tests.

## Fixture Bundle

- Path: `tests/fixtures/data/core_seed_bundle.json`
- Coverage:
  - Multiple firms, funds, and documents
  - Correction history entries tied to provenance pointers

## Load + Reset Workflow

1. Apply core schema migration (`apply_core_schema`) on a sqlite connection.
2. Load fixture JSON with `load_seed_fixture`.
3. Insert seed rows with `load_core_seed_rows`.
4. Reset tables with `reset_core_seed_tables` before reloading.

Reference implementation:
- `src/inv_man_intake/data/fixtures.py`
- `tests/data/test_schema_integrity.py::test_seed_fixture_reset_supports_repeatable_loads`

## Contract Checks

- Foreign-key integrity and orphan prevention:
  - `tests/data/test_schema_integrity.py::test_integrity_checks_reject_orphaned_rows`
- Correction history ordering:
  - `tests/data/test_schema_integrity.py::test_correction_history_returns_ordered_events`
- Provenance pointer validity:
  - `tests/data/test_schema_integrity.py::test_provenance_pointer_validation_accepts_known_document_fields`
  - `tests/data/test_schema_integrity.py::test_provenance_pointer_validation_flags_unknown_targets`
