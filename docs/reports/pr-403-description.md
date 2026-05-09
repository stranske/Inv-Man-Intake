## Summary
- References audit artifact: `docs/reports/v1_smoke_contract_audit.md`.
- Documents per-instance follow-up issue coverage from the audit scope:
  - #379 (intake persistence)
  - #380 (real document-bytes extraction)
  - #381 (queue reconciliation)
- Additional per-instance follow-up issues created by this audit: none.

## Testing
- `python -m pytest tests/v1/test_smoke_contract_coverage.py tests/test_v1_acceptance_smoke.py --no-cov`
