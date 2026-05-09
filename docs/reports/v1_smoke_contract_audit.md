# V1 Smoke Contract Audit

Issue: #382
Updated: 2026-05-09

## Summary

The v1 acceptance smoke now exercises the intended intake-to-scoring path rather than the older fixture/orphan substitutes called out by the repo-review issue. The three converged per-instance fixes are already represented in the repository history:

- Intake persistence: issue #379 / PR #393 replaced dict-only registration evidence with `register_intake_bundle_file(..., core_repository=..., document_store=...)` and repository/store assertions.
- Real-byte extraction: issue #380 / PR #399 routes committed PDF bytes through `PdfPrimaryExtractionProvider` and the extraction orchestrator.
- Queue reconciliation: issue #381 / PR #400 made `workflow_validation.py` the canonical validation queue state model and removed the orphan `queue/state_machine.py` path.

No new follow-up issues were filed from this audit because the remaining v1-smoke-relevant non-end-to-end findings are already covered by those converged issue/PR pairs. Contracts that are not claimed by the v1 smoke are listed separately so they do not get mistaken for smoke regressions.

## Audit Table

| Contract | Smoke disposition | Evidence | Disposition |
| --- | --- | --- | --- |
| `docs/contracts/intake_contract.md` | end-to-end | `src/inv_man_intake/v1_smoke.py` loads `tests/fixtures/intake/pdf_primary_mixed_bundle.json` through `register_intake_bundle_file`; `tests/test_v1_acceptance_smoke.py` asserts stable package/document IDs. | Covered by issue #379 / PR #393. |
| `docs/contracts/core_schema.md` | end-to-end | `run_v1_smoke_pipeline` constructs `CoreRepository(sqlite3.connect(":memory:"))`; the smoke asserts firm, fund, and four document rows plus document metadata. | Covered by issue #379 / PR #393. |
| `docs/contracts/core_schema_migration.md` | not a v1-smoke claim | The smoke verifies repository behavior against an in-memory schema, not migration apply/rollback mechanics. | No follow-up from this audit; migration coverage is outside v1 smoke scope. |
| `docs/contracts/extraction_provider_contract.md` | end-to-end | `_run_extraction_smoke` instantiates `PdfPrimaryExtractionProvider`, adapts it into `ExtractionOrchestrator`, and returns an `ExtractedDocumentResult` from committed PDF bytes. | Covered by issue #380 / PR #399. |
| `docs/contracts/extraction_thresholds.md` | end-to-end | `run_v1_smoke_pipeline` evaluates `ThresholdConfig`, attaches a threshold summary, and asserts `low_key_field_coverage` escalation evidence in the smoke test. | No new follow-up needed. |
| `docs/contracts/performance_normalization.md` | end-to-end | The smoke resolves conflicting XLSX/deck series, normalizes monthly points, computes benchmark-aligned metrics, and asserts missing-month and observation counts. | No new follow-up needed. |
| `docs/contracts/queue_states.md` | end-to-end | The canonical state contract now points at `workflow_validation.py`; issue #381 removed the orphan `queue/state_machine.py` path and added state transition coverage. | Covered by issue #381 / PR #400. |
| `docs/contracts/queue_assignment_sla.md` | end-to-end for analyst-first assignment | The smoke creates `create_analyst_first_assignment(...)` for the performance-conflict queue item and asserts analyst ownership/event evidence. | No new follow-up needed for the smoke claim; ops reassignment and breach scheduling remain separate queue concerns. |
| `docs/contracts/scoring_explainability.md` | end-to-end | The smoke computes a score, builds an explainability payload with component rationales, formats it, and asserts score/payload reconciliation. | No new follow-up needed. |
| `docs/contracts/provenance_history.md` | not a v1-smoke claim | The smoke asserts extraction field source-document and source-page provenance, but it does not claim append-only human correction history. | No follow-up from this audit; correction-history behavior is outside this smoke path. |
| `docs/contracts/agent-runner-output.md` | not a v1-smoke claim | This contract describes automation runner output, not the product v1 intake readiness pipeline. | Not part of this audit scope. |

## Regression Gate

`tests/v1/test_smoke_contract_coverage.py` now guards the specific drift modes that caused this audit:

- inline fixture primary providers such as `fixture-primary` in `src/inv_man_intake/v1_smoke.py`;
- calls to `register_intake_bundle` or `register_intake_bundle_file` without both `core_repository` and `document_store`;
- imports from the discarded `inv_man_intake.queue.state_machine` module.

The guard includes synthetic positive cases proving each violation family is rejected. It complements the full smoke test in `tests/test_v1_acceptance_smoke.py`, which remains the executable end-to-end proof.

## Follow-Up Issue Disposition

Existing converged issue coverage:

- #379: intake/core persistence drift, merged through PR #393.
- #380: real document-bytes extraction drift, merged through PR #399.
- #381: validation queue state drift, merged through PR #400.

Additional follow-ups filed by this audit: none. The currently observed v1-smoke-relevant drift has already been represented by the issue/PR set above, and the new guard prevents those exact shortcuts from returning.
