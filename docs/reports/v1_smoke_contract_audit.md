# V1 Smoke Contract Audit

Issue: #382
Updated: 2026-05-10

## Verifier Disposition

PR #403 delivered the executable fixes for issue #382, but provider comparison flagged this report as too thin to prove every relevant v1 smoke contract row had been audited. This follow-up expands the audit evidence without changing the v1 smoke runtime path.

The audit conclusion is unchanged: the v1 acceptance smoke now exercises the intended intake-to-scoring path instead of the older fixture/orphan shortcuts, and no additional v1-smoke-relevant follow-up issue is required beyond the converged issue set listed below.

## Audit Scope Boundary

This audit covers the local v1 acceptance smoke path from accepted package intake through repository persistence, real-byte extraction, thresholding, performance normalization, queue assignment, scoring, explainability, and trace continuity.

The audit does not claim coverage for standalone migration runners, append-only provenance correction history, external agent-runner output artifacts, full queue operations reassignment, or SLA scheduling. Those contracts are recorded as outside the v1 smoke claim so they are not misreported as smoke regressions. No issue is filed from this audit for an outside-scope row unless that row exposes a concrete v1 smoke acceptance gap.

## Contract File Inventory

The v1 smoke audit enumerates every contract under `docs/contracts/` and marks whether it is in scope for this smoke evidence pass.

| Contract file | In v1 smoke audit scope | Notes |
| --- | --- | --- |
| `docs/contracts/intake_contract.md` | yes | Canonical intake payload and metadata/file requirements. |
| `docs/contracts/core_schema.md` | yes | Repository hierarchy and document linkage used by smoke persistence checks. |
| `docs/contracts/extraction_provider_contract.md` | yes | Primary provider identity/result shape and secondary boundary handling. |
| `docs/contracts/queue_states.md` | yes | Canonical queue-state path and orphan-module exclusion. |
| `docs/contracts/queue_assignment_sla.md` | yes | Analyst-first queue assignment exercised; ops/SLA scheduling rows scoped out. |
| `docs/contracts/performance_normalization.md` | yes | Period normalization, conflict resolution, and benchmark correlation. |
| `docs/contracts/scoring_explainability.md` | yes | Final score and explainability payload checks. |
| `docs/contracts/extraction_thresholds.md` | yes | Threshold evaluation and escalation evidence. |
| `docs/contracts/provenance_history.md` | yes | Source-location trace row in scope; correction history row outside v1 smoke. |
| `docs/contracts/core_schema_migration.md` | yes | Audited as outside v1 smoke because migration runner is not invoked. |
| `docs/contracts/agent-runner-output.md` | yes | Audited as outside v1 smoke because runner artifact contract is not invoked. |
| `docs/contracts/image_classification.md` | yes | Audited as not-exercised by v1 acceptance smoke; dedicated coverage lives in `tests/images/` for classifier, feedback, extractor, service, and report behavior. |

## Converged Follow-Up Mapping

| Finding family | Issue | PR | Current disposition |
| --- | --- | --- | --- |
| Intake/core persistence was previously asserted through dict-only smoke evidence. | #379 | #393 | Converged; `register_intake_bundle_file(..., core_repository=..., document_store=...)` is used and repository/store assertions are in the smoke test. |
| Extraction was previously allowed to stay on fixture-primary evidence instead of committed PDF bytes. | #380 | #399 | Converged; committed fixture PDF bytes route through `PdfPrimaryExtractionProvider` and the extraction orchestrator. |
| Queue state coverage previously referenced the discarded orphan queue path. | #381 | #400 | Converged; `workflow_validation.py` is the canonical validation queue state path and the orphan `queue/state_machine.py` path is guarded against. |
| Additional v1-smoke-relevant row needing a new issue. | None | None | No issue filed; audited rows are either covered by the converged set, already have direct smoke evidence, or are outside the v1 smoke claim. |

## Contract Row Matrix

| Contract row | Contract source | Smoke disposition | Evidence | Follow-up disposition |
| --- | --- | --- | --- | --- |
| `intake.metadata.required_fields` | `docs/contracts/intake_contract.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:95-100` calls `register_intake_bundle_file` with repository and document store dependencies. `tests/test_v1_acceptance_smoke.py:38-56` asserts accepted package identity, stable IDs, persisted firm/fund/document rows, and document metadata. | Covered by #379 / PR #393. |
| `intake.files.roles_and_source_refs` | `docs/contracts/intake_contract.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:95-100` registers committed bundle files. `tests/test_v1_acceptance_smoke.py:38-56` asserts the accepted package and stored document metadata needed by downstream source references. | Covered by #379 / PR #393. |
| `core_schema.repository_hierarchy` | `docs/contracts/core_schema.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:88` constructs `CoreRepository(sqlite3.connect(":memory:"))`. `tests/test_v1_acceptance_smoke.py:43-56` asserts firm, fund, and document row counts. | Covered by #379 / PR #393. |
| `core_schema.document_store_linkage` | `docs/contracts/core_schema.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:89` constructs `InMemoryDocumentStore`. `tests/test_v1_acceptance_smoke.py:54-56` asserts persisted document bytes/hash linkage. | Covered by #379 / PR #393. |
| `core_schema.versioned_documents` | `docs/contracts/core_schema.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:95-100` routes bundle registration through persistence-backed intake integration. `tests/test_v1_acceptance_smoke.py:54-56` asserts stable document metadata after registration, proving versioned records are preserved instead of dict-only fixtures. | Covered by #379 / PR #393. |
| `core_schema_migration.apply_rollback` | `docs/contracts/core_schema_migration.md` | not-exercised | `src/inv_man_intake/v1_smoke.py` uses an in-memory repository for the acceptance path, and `tests/test_v1_acceptance_smoke.py` has no migration apply/rollback assertion. | No issue filed from this audit; migration runners are outside the v1 smoke claim. |
| `extraction.provider_identity` | `docs/contracts/extraction_provider_contract.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:244-273` routes committed fixture PDF bytes through `PdfPrimaryExtractionProvider`. `tests/test_v1_acceptance_smoke.py:66-70` asserts provider identity `pdf-primary`. | Covered by #380 / PR #399. |
| `extraction.canonical_result_fields` | `docs/contracts/extraction_provider_contract.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:244-273` returns canonical extraction results. `tests/test_v1_acceptance_smoke.py:60-75` asserts confidence, source document, source page, provider, escalation, and evidence fields. | Covered by #380 / PR #399. |
| `extraction.secondary_fallback_route` | `docs/contracts/extraction_provider_contract.md` | fixture-stand-in | `src/inv_man_intake/v1_smoke.py:116-129` captures the primary run and unresolved fallback route. `tests/test_v1_acceptance_smoke.py:69-70` asserts unresolved `fixture-fallback` secondary coverage. | No issue filed; the smoke asserts the expected unsupported secondary boundary. |
| `extraction_thresholds.low_key_field_coverage` | `docs/contracts/extraction_thresholds.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:130-156` builds `ThresholdConfig`, evaluates thresholds, and attaches the threshold summary. `tests/test_v1_acceptance_smoke.py:70-75` asserts escalation and `low_key_field_coverage` evidence. | No issue filed; direct smoke evidence exists. |
| `extraction_thresholds.document_escalation` | `docs/contracts/extraction_thresholds.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:130-156` attaches document-level threshold outcome. `tests/test_v1_acceptance_smoke.py:70-75` asserts document escalation state. | No issue filed; direct smoke evidence exists. |
| `performance_normalization.input_periods` | `docs/contracts/performance_normalization.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:164-178` normalizes performance observations. `tests/test_v1_acceptance_smoke.py:78-90` asserts canonical month and observation count. | No issue filed; direct smoke evidence exists. |
| `performance_normalization.conflict_resolution` | `docs/contracts/performance_normalization.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:164-178` resolves conflicts and computes metrics. `tests/test_v1_acceptance_smoke.py:78-90` asserts conflict count and benchmark correlation. | No issue filed; direct smoke evidence exists. |
| `performance_normalization.benchmark_correlation` | `docs/contracts/performance_normalization.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:164-178` carries benchmark metadata through metrics. `tests/test_v1_acceptance_smoke.py:78-90` asserts benchmark correlation. | No issue filed; direct smoke evidence exists. |
| `queue_states.validation_queue_state` | `docs/contracts/queue_states.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:186-195` builds the validation queue item through canonical workflow validation code. `tests/test_v1_acceptance_smoke.py:92-100` asserts queue owner, assignment event, and conflict evidence linkage. | Covered by #381 / PR #400. |
| `queue_states.orphan_state_machine_absence` | `docs/contracts/queue_states.md` | orphan-only | `tests/v1/test_smoke_contract_coverage.py` rejects imports from `inv_man_intake.queue.state_machine`. | Covered by #381 / PR #400. |
| `queue_assignment_sla.analyst_first_assignment` | `docs/contracts/queue_assignment_sla.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:186-195` calls `create_analyst_first_assignment`. `tests/test_v1_acceptance_smoke.py:92-100` asserts analyst owner and default assignment note. | No issue filed; direct smoke evidence exists. |
| `queue_assignment_sla.ops_reassignment` | `docs/contracts/queue_assignment_sla.md` | not-exercised | The v1 smoke path exercises analyst-first assignment for a validation item, not ops reassignment flows. | No issue filed from this audit; ops reassignment is outside the v1 smoke claim. |
| `queue_assignment_sla.sla_breach_scheduling` | `docs/contracts/queue_assignment_sla.md` | not-exercised | The v1 smoke path does not schedule or age SLA breach jobs. | No issue filed from this audit; SLA scheduling is outside the v1 smoke claim. |
| `scoring_explainability.final_score` | `docs/contracts/scoring_explainability.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:202-219` computes scores and builds explainability. `tests/test_v1_acceptance_smoke.py:102-109` asserts final score and payload consistency. | No issue filed; direct smoke evidence exists. |
| `scoring_explainability.driver_payload` | `docs/contracts/scoring_explainability.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:202-219` formats explainability drivers. `tests/test_v1_acceptance_smoke.py:102-109` asserts explainability payload values. | No issue filed; direct smoke evidence exists. |
| `provenance_history.source_location_trace` | `docs/contracts/provenance_history.md` | end-to-end | `src/inv_man_intake/v1_smoke.py:244-273` carries source locations from provider extraction results into the smoke payload. `tests/test_v1_acceptance_smoke.py:60-75` asserts source document and source page values. | No issue filed; source-location trace is covered by #380 / PR #399. |
| `provenance_history.field_corrections` | `docs/contracts/provenance_history.md` | not-exercised | The v1 smoke does not write append-only correction history records. | No issue filed from this audit; correction-history behavior is outside the v1 smoke claim. |
| `agent-runner-output.workflow_call_outputs` | `docs/contracts/agent-runner-output.md` | not-exercised | No call site exists in `src/inv_man_intake/v1_smoke.py`; this contract targets automation runner output artifacts rather than app smoke behavior. | No issue filed from this audit; runner output artifacts are outside the v1 smoke claim. |
| `smoke_trace.continuity` | v1 smoke acceptance path | end-to-end | `src/inv_man_intake/v1_smoke.py:372-379` assembles the cross-stage smoke trace vector from intake, extraction, normalization, queue, and scoring stages. `tests/test_v1_acceptance_smoke.py:111-116` asserts those exact trace markers. | No issue filed; direct smoke evidence exists. |

## Regression Gate Details

`tests/v1/test_smoke_contract_coverage.py` guards the drift modes that caused issue #382:

- inline fixture primary providers such as `fixture-primary` or `fixture_primary` in `src/inv_man_intake/v1_smoke.py`;
- calls to `register_intake_bundle` or `register_intake_bundle_file` without both `core_repository` and `document_store`;
- imports from the discarded `inv_man_intake.queue.state_machine` module;
- audit regressions that remove row-level contract evidence, scope boundaries, follow-up mapping, or outside-scope dispositions.

The guard includes synthetic positive cases proving each violation family is rejected. It complements `tests/test_v1_acceptance_smoke.py`, which remains the executable end-to-end proof of the accepted path.

## No New Follow-Up Rationale

No additional per-instance follow-up issue is filed from this audit because:

- every v1-smoke-relevant regression family found by the review is already represented by #379, #380, or #381 and their merged PRs;
- rows with direct smoke evidence now identify the runtime call site and assertion site;
- rows outside the v1 smoke claim are explicitly scoped out and marked "No issue filed from this audit" rather than left ambiguous;
- the regression guard prevents the same fixture-primary, dict-only registration, and orphan queue shortcuts from returning.

Additional per-instance follow-up issues created by this audit: none.
