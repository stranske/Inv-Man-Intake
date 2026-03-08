# Intake Fixture Catalog

This catalog maps the issue #19 intake fixture corpus to expected registration outcomes.

## v1 Input Class Coverage

| Fixture | Input class | Expected outcome | Deterministic errors |
| --- | --- | --- | --- |
| `tests/fixtures/intake/pdf_primary_bundle.json` | `parseable_pdf_primary_only` | Accepted (`accepted=true`, `status=received`, `package_id=pkg_pdf_primary_001`, `file_count=1`) | None |
| `tests/fixtures/intake/pdf_primary_mixed_bundle.json` | `parseable_pdf_primary_mixed_secondary` | Accepted (`accepted=true`, `status=received`, `package_id=pkg_pdf_mixed_001`, `file_count=4`) | None |
| `tests/fixtures/intake/pptx_primary_mixed_bundle.json` | `parseable_pptx_primary_mixed_secondary` | Accepted (`accepted=true`, `status=received`, `package_id=pkg_pptx_mixed_001`, `file_count=3`) | None |
| `tests/fixtures/intake/malformed_missing_metadata.json` | `malformed_missing_required_metadata` | Rejected (`accepted=false`, `status=None`, `package_id=pkg_missing_metadata_001`) | `missing_required_metadata` (`metadata.fund_name`, `metadata.received_at`), `invalid_received_at` (`metadata.received_at`) |
| `tests/fixtures/intake/malformed_unsupported_type.json` | `malformed_unsupported_file_type_and_missing_primary` | Rejected (`accepted=false`, `status=None`, `package_id=pkg_unsupported_type_001`) | `unsupported_file_type` (`files[0].file_name`), `missing_primary_document` (`files`) |
| `tests/fixtures/intake/malformed_corrupted_file.json` | `malformed_invalid_json_bundle` | Rejected (`accepted=false`, `status=None`, `package_id=None`) | `invalid_json_bundle` (bundle path) |

## Notes

- `tests/intake/test_ingest_integration.py` is the canonical integration test entrypoint for the registration outcomes listed above.
- The malformed fixtures are expected to fail deterministically with stable error codes and paths.

## Integration test entrypoint

- `tests/intake/test_ingest_integration.py`
  - Covers success path registration for valid bundles.
  - Covers graceful rejection + deterministic errors for malformed bundles.
