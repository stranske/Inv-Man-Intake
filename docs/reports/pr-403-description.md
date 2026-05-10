## Summary
- References audit artifact: `docs/reports/v1_smoke_contract_audit.md`.
- Adds the verifier follow-up expansion requested after PR #403: explicit scope boundary, row-level contract matrix, and no-new-issue rationale.
- Documents per-instance follow-up issue coverage from the audit scope:
  - #379 (intake persistence)
  - #380 (real document-bytes extraction)
  - #381 (queue reconciliation)
- Additional per-instance follow-up issues created by this audit: none.
- Acceptance criterion status: [x] PR description references the audit artifact, enumerates per-instance follow-up issues, and explains why no additional issue was filed from the v1 smoke audit.

## Testing
- `python -m pytest tests/v1/test_smoke_contract_coverage.py tests/test_v1_acceptance_smoke.py --no-cov`
