# Production vs smoke audit (`run_pipeline` path)

Audit date: 2026-10-17. Scope: every reachable `smoke_mode` branch and fixed
identifier / document assumption from `inv_man_intake.run.run_pipeline` through
`inv_man_intake.v1_smoke._run_pipeline_core` when `expected_document_ids` is
omitted (production / headless CLI). Smoke-only behavior applies when
`expected_document_ids` is provided (`run_v1_smoke_pipeline`).

This audit inventories and classifies only. It does **not** relocate
`v1_smoke.py`, bundle production repairs, or auto-file follow-up issues.
Per-instance fixes ship separately.

Historical readiness-smoke audit: `docs/reports/v1_smoke_contract_audit.md`
(#382). This document is limited to remaining production `run_pipeline` seams.

## Entry discriminator

| Signal | Production (`run_pipeline`) | Smoke (`run_v1_smoke_pipeline`) |
| --- | --- | --- |
| `expected_document_ids` | omitted / `None` → `smoke_mode=False` | required tuple → `smoke_mode=True` |
| Source | `src/inv_man_intake/run.py` (`run_pipeline` → `_run_pipeline_core`) | `src/inv_man_intake/v1_smoke.py` (`run_v1_smoke_pipeline`) |
| Gate line | `v1_smoke.py` `smoke_mode = expected_document_ids is not None` | same |

## Reachable branches and fixed assumptions

Columns:

- **Source** — current-head anchor in `v1_smoke.py` / `run.py`
- **Production contract** — required headless behavior
- **Evidence class** — intentional smoke control / prevention assertion /
  confirmed production gap / superseded review claim / architectural seam /
  unknown (needs human)
- **Classification evidence** — existing tests used for this audit
- **Disposition** — keep / return for human / already covered by owner

| ID | Source | Condition | Production contract | Smoke behavior | Evidence class | Classification evidence | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | `v1_smoke.py` `smoke_mode = …` | `expected_document_ids is not None` | Production must omit IDs so `smoke_mode` is false | IDs required; hard package asserts | prevention assertion | `test_run_pipeline_invokes_core_without_smoke_document_ids` | keep gate; production OK |
| B02 | `v1_smoke.py` content_resolver | `smoke_mode` | `filesystem_content_resolver(content_root)` | `None` (fixture-relative) | intentional smoke control | `test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout` | keep smoke; production OK |
| B03 | `v1_smoke.py` registration branch | `expected_document_ids is None` | Rejected bundle → `ValueError` | `_assert_registered_package_state` | intentional smoke control | CLI nonzero on bad bundles (`test_ingest_entrypoint_returns_nonzero_for_missing_bundle`, escape reject) | keep; production OK |
| B04 | `v1_smoke.py` `_pipeline_document_bytes` | `smoke_mode` | Read bytes from `document_store` | `_fixture_bytes` under `tests/fixtures/extraction` | intentional smoke control | `test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout` (forbids `_fixture_bytes` / `_fixture_performance_series` on production path) | keep smoke; production OK |
| B05 | `v1_smoke.py` secondary content | `smoke_mode` and secondary present | Store bytes for secondary | Substitutes `summit_arc_track_record.xlsx` fixture bytes | intentional smoke control | `test_ingest_secondary_boundary_uses_submitted_workbook_bytes_and_id` (submitted bytes and registered ID in both document orders); `test_ingest_primary_with_non_workbook_secondary` (non-xlsx never enters boundary) | keep smoke; production OK |
| B06 | `v1_smoke.py` `_resolve_performance_series` | `smoke_mode` | Workbook from registered docs; deck/benchmark `None` | `_fixture_performance_series()` (xlsx+deck+benchmark) | intentional smoke control | `test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout`; `test_ingest_performance_smoke_retains_fixture_returns` | keep smoke; production OK |
| B07 | `v1_smoke.py` `performance["source"]` | `smoke_mode` | `"submitted_workbook"` | `"smoke_fixture"` | prevention assertion | `test_production_performance_source_deliberate_smoke_fixture_fails`; `test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout` | keep prevention |
| B08 | `v1_smoke.py` scoring `if not smoke_mode` | production | `_evidence_backed_score_components` + `gate_scoring_submission` + `compute_score` when evidence meets mins; else unavailable explainability | N/A (other branch) | intentional production path (post-#1019 seam) | `tests/cli/test_ingest_entrypoint.py` (`test_ingest_score_numeric_for_two_supported_asset_classes`, `test_ingest_score_insufficient_evidence_is_unavailable`); `tests/scoring/test_engine.py` (`test_compute_score_is_deterministic_for_identical_inputs`, `test_asset_class_weight_sets_produce_materially_different_scores`) | keep; not a smoke stub |
| B09 | `v1_smoke.py` scoring `if smoke_mode` | smoke | N/A | Hardcoded `_score_components` (0.80/0.78/0.69/0.74 + correlation) + asset_class `"credit"` | intentional smoke control | `test_ingest_performance_smoke_retains_fixture_returns`; `test_ingest_score_deliberate_break_constants_would_fail`; engine rejects unknown classes via `tests/scoring/test_engine.py` `test_compute_score_rejects_unmapped_asset_class` | keep smoke-only; production must not use |
| B10 | `v1_smoke.py` queue assignment | `smoke_mode` | Unowned pending-triage items from real extraction outcomes; UTC clock; replayable local handoff | Fixed analyst and date in smoke only | **production path repaired by #1018 / #1034** | `test_production_queue_assignment_is_unowned_and_uses_live_clock`; queue artifact replay tests | retain local handoff contract; source #1018 verifier disposition |
| B11 | `v1_smoke.py` `_workbook_performance_series` return | production track-record path | `(xlsx, None, None)` — no deck/benchmark | Fixture supplies deck+benchmark | **confirmed production gap** | `test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout` asserts `comparison_available is False` / `benchmark_available is False` | return for human / performance owner; **no auto-filed issue** |
| B12 | `v1_smoke.py` / `run.py` stores | always | Ephemeral `:memory:` SQLite + `InMemoryDocumentStore` for CLI run | same | architectural seam | Documented in `docs/runbooks/headless_ingest.md`; #382 readiness | out of scope for this audit; not smoke-gated |
| B13 | `run.py` `allow_remote_tracing=False` | always from `run_pipeline` | Local spans only | Smoke API may opt in | intentional / prevention | `test_ingest_ignores_langsmith_key_when_tracing_disabled`; `test_run_pipeline_disables_remote_tracing` | keep; production OK |
| B14 | `v1_smoke.py` `_run_secondary_extraction_boundary_smoke` | secondary workbook selected | Unsupported-secondary boundary (ops_review) for xlsx secondary | same call; smoke may feed fixture bytes (B05) | intentional smoke control (boundary) | `test_ingest_primary_with_non_workbook_secondary` | keep boundary; not a silent production stub |
| B15 | `v1_smoke.py` `_run_extraction_smoke` PDF service | primary `.pdf` | Uses `build_legacy_pdf_fixture_service` for this shared path | same | mixed / historical corpus seam | `test_ingest_primary_only_pdf_and_pptx`; `test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout` | return for human / extraction owner if Doc-Lineage-only production is required; **no auto-filed issue** |
| B16 | `v1_smoke.py` `_select_extraction_documents` | always | Select primary by `PRIMARY_EXTENSIONS` + preferred workbook by role; order-independent | same | **superseded review claim** | `test_ingest_file_order_permutations_equivalent`; `test_ingest_primary_only_pdf_and_pptx` | review-time `document_ids[0]`/`[1]` / two-doc guard **no longer present** |
| B17 | `v1_smoke.py` threshold key field tuple | always | Shared mandatory field set for threshold profile | same | intentional shared policy | `tests/run/test_pipeline_threshold_config.py` | keep; not smoke-gated |
| B18 | `v1_smoke.py` orchestrator `fixture-fallback` | primary extract | Named fallback route on primary failure | same | intentional / OCR-fallback partial | `test_ingest_primary_with_non_workbook_secondary`; Codex “OCR/fallback” partial — unknown near-term OCR adapter scope | unknown whether a separate production OCR adapter is in near-term scope — **return for human**; **no auto-filed issue** |
| B19 | `v1_smoke.py` `_explainability_inputs` analyst provenance | smoke components without provenances | Production passes explicit provenances | Defaults to `analyst_001` provenance | intentional smoke control | `test_ingest_score_explainability_provenance_is_resolvable`; `test_ingest_score_deliberate_break_constants_would_fail` | keep smoke-only |
| B20 | `v1_smoke.py` fleet `model="deterministic-pdf-parser"` | always | Telemetry label for this path | same | architectural seam | fleet builders; not asserted as a score/queue stub in `tests/cli/test_ingest_entrypoint.py` | out of scope; not a silent score/queue stub |

## Classification summary

| Class | IDs |
| --- | --- |
| Intentional smoke controls (retain) | B02, B03, B04, B05, B06, B09, B14, B19 |
| Prevention assertions (tests must hold) | B01, B07, B13 |
| Production path OK / shared policy | B08, B10, B17 |
| Confirmed gaps → product review (no auto-file) | B11 |
| Superseded review claim | B16 |
| Architectural / mixed / unknown | B12, B15, B18, B20 |

## Linked approved owners (known gaps; no new issues filed)

| Gap | Owner area | Existing reference | Notes |
| --- | --- | --- | --- |
| Historical fixed analyst queue assignment | queue / validation assignment | #1018 / merged #1034; `docs/contracts/queue_states.md` | Repaired: local replayable unowned pending-triage items with actual UTC timestamps; smoke fixture retains its fixed analyst/date |
| Cross-source performance comparison unavailable | performance / ingest | `docs/contracts/performance_normalization.md`; production returns deck/benchmark `None` | Confirm whether deck/benchmark ingest is near-term scope |
| Ephemeral stores in headless CLI | persistence / ops | `docs/runbooks/headless_ingest.md`; #382 | Documented seam; not introduced by this audit |
| Primary PDF legacy fixture service on shared path | extraction | `docs/contracts/extraction_service.md`; #380 / #9 family | Confirm Doc-Lineage-only requirement for arbitrary packages |
| OCR / fallback adapter beyond named fixture-fallback | extraction | `docs/contracts/extraction_provider_contract.md` fallback section | Confirm near-term OCR adapter scope |

Scoring evidence-backed production path (B08) is already exercised by CLI score-bundle tests; smoke hardcoded components (B09) remain smoke-only. Historical #1019 described an earlier `score=None`-only production branch; current head derives scores when evidence thresholds are met.

## Uncovered items returned for human review

No automatic follow-up issues are created from this audit.

1. **Queue placeholder (B10), resolved by #1034** — production uses the local versioned queue handoff from #1018. No service/API selection is needed for that delivered contract; original source acceptance remains verifier-owned.
2. **Deck/benchmark comparison (B11)** — production workbook path does not populate deck/benchmark series; confirm near-term scope outside smoke fixtures.
3. **Primary PDF service selection (B15)** — shared path still selects `build_legacy_pdf_fixture_service` for `.pdf`; confirm whether arbitrary production PDFs must use Doc-Lineage exclusively.
4. **OCR/fallback route (B18)** — named `fixture-fallback` / secondary unsupported route remain; confirm whether a dedicated production OCR adapter is in scope.

## Prevention coverage (this PR)

- `tests/cli/test_ingest_entrypoint.py`
  - `test_run_pipeline_invokes_core_without_smoke_document_ids` — production never passes `expected_document_ids`.
  - `test_run_pipeline_disables_remote_tracing` — production always passes `allow_remote_tracing=False`.
  - `test_ingest_score_never_calls_smoke_components` — production never invokes fixed smoke score components, with either sufficient or insufficient scoring evidence.
  - `test_ingest_primary_uses_submitted_bytes_filename_and_id` — renamed PDF and PowerPoint submissions reach extraction with their submitted bytes and registered IDs in both document orders; emitted fields and evidence retain those IDs.
  - `test_ingest_secondary_boundary_uses_submitted_workbook_bytes_and_id` — secondary extraction receives the renamed submitted workbook's bytes and registered document ID in both document orders, with a non-fixture package ID.
  - `test_production_performance_source_deliberate_smoke_fixture_fails` — mutation of performance `source` to `smoke_fixture` fails the prevention assertion; restoring `submitted_workbook` passes.
  - Existing layout / non-workbook / score deliberate-break tests continue to forbid fixture helpers and smoke constants on the headless path.
- `tests/scoring/test_engine.py` — scoring engine invariants (unchanged by this audit).
