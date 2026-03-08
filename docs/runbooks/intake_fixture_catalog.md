# Intake Fixture Catalog

This catalog maps the issue #19 intake fixture corpus to expected registration outcomes.

## Fixture set

- `tests/fixtures/intake/pdf_primary_bundle.json`
  - Valid PDF-primary package with required metadata and one primary file.
  - Expected: registration accepted with `status=received`.
- `tests/fixtures/intake/pptx_primary_mixed_bundle.json`
  - Valid PPTX-primary package with mixed secondary files (`xlsx`, `txt`).
  - Expected: registration accepted with `status=received`.
- `tests/fixtures/intake/malformed_missing_metadata.json`
  - Missing required metadata fields (`fund_name`, `received_at`).
  - Expected: deterministic validation rejection (`missing_required_metadata`, `invalid_received_at`).
- `tests/fixtures/intake/malformed_unsupported_type.json`
  - Unsupported file extension (`.zip`) with no primary PDF/PPTX file.
  - Expected: deterministic validation rejection (`unsupported_file_type`, `missing_primary_document`).
- `tests/fixtures/intake/malformed_corrupted_file.json`
  - Intentionally malformed JSON payload for parse-failure path.
  - Expected: deterministic parse rejection (`invalid_json_bundle`).

## Integration test entrypoint

- `tests/intake/test_ingest_integration.py`
  - Covers success path registration for valid bundles.
  - Covers graceful rejection + deterministic errors for malformed bundles.
