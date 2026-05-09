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
| `docs/contracts/intake_contract.md` | end-to-end | Call site: `src/inv_man_intake/v1_smoke.py:94-99` (`register_intake_bundle_file(..., core_repository=..., document_store=...)`). Assertion: `tests/test_v1_acceptance_smoke.py:37-55` (accepted package, stable IDs, persisted bytes/hash linkage). | Covered by issue #379 / PR #393. |
| `docs/contracts/core_schema.md` | end-to-end | Call site: `src/inv_man_intake/v1_smoke.py:87` (`CoreRepository(sqlite3.connect(":memory:"))`). Assertion: `tests/test_v1_acceptance_smoke.py:42-55` (firm/fund/document row counts and document metadata). | Covered by issue #379 / PR #393. |
| `docs/contracts/core_schema_migration.md` | not-exercised | Absence: `src/inv_man_intake/v1_smoke.py` uses in-memory repository setup only (`:87`) and `tests/test_v1_acceptance_smoke.py` has no migration apply/rollback assertion path. | No follow-up from this audit; migration coverage is outside v1 smoke scope. |
| `docs/contracts/extraction_provider_contract.md` | end-to-end | Call site: `src/inv_man_intake/v1_smoke.py:228-257` (provider + orchestrator run on fixture PDF bytes). Assertion: `tests/test_v1_acceptance_smoke.py:67-69` (provider `pdf-primary`, unresolved secondary route surfaced). | Covered by issue #380 / PR #399. |
| `docs/contracts/extraction_thresholds.md` | end-to-end | Call site: `src/inv_man_intake/v1_smoke.py:129-150` (`ThresholdConfig`, `evaluate_thresholds`, `attach_threshold_summary`). Assertion: `tests/test_v1_acceptance_smoke.py:70-75` (document escalation and `low_key_field_coverage` evidence field). | No new follow-up needed. |
| `docs/contracts/performance_normalization.md` | end-to-end | Call site: `src/inv_man_intake/v1_smoke.py:163-172` (conflict resolution + normalization + metrics). Assertion: `tests/test_v1_acceptance_smoke.py:81-89` (conflict count, canonical month, observation counts, benchmark correlation). | No new follow-up needed. |
| `docs/contracts/queue_states.md` | end-to-end | Call site: `src/inv_man_intake/v1_smoke.py:174-178` (`create_analyst_first_assignment` on validation queue item). Assertion: `tests/test_v1_acceptance_smoke.py:91-99` (queue ownership, assignment event, conflict evidence linkage). | Covered by issue #381 / PR #400. |
| `docs/contracts/queue_assignment_sla.md` | end-to-end for analyst-first assignment | Call site: `src/inv_man_intake/v1_smoke.py:174-178` (analyst-first assignment construction). Assertion: `tests/test_v1_acceptance_smoke.py:91-99` (analyst owner + default assignment note). | No new follow-up needed for the smoke claim; ops reassignment and breach scheduling remain separate queue concerns. |
| `docs/contracts/scoring_explainability.md` | end-to-end | Call site: `src/inv_man_intake/v1_smoke.py:191-203` (score compute + explainability build/format). Assertion: `tests/test_v1_acceptance_smoke.py:104-108` (final score and explainability payload consistency). | No new follow-up needed. |
| `docs/contracts/provenance_history.md` | not-exercised | Boundary assertion only: `tests/test_v1_acceptance_smoke.py:60-66,190-205` verifies extraction source-doc/page provenance, but there is no call/assertion over append-only correction history writes. | No follow-up from this audit; correction-history behavior is outside this smoke path. |
| `docs/contracts/agent-runner-output.md` | not-exercised | Absence: no call site in `src/inv_man_intake/v1_smoke.py` and no assertion in `tests/test_v1_acceptance_smoke.py`; the contract targets automation-runner output artifacts. | Not part of this audit scope. |

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
