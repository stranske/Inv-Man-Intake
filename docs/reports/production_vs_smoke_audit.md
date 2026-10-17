# Production vs smoke audit (`run_pipeline` path)

Audit date: 2026-10-17. Scope: branches and stand-ins reachable from
`inv_man_intake.run.run_pipeline` through `v1_smoke._run_pipeline_core` when
`expected_document_ids` is omitted (production / headless CLI). Smoke-only
behavior is retained where `expected_document_ids` is provided
(`run_v1_smoke_pipeline`).

## Entry discriminator

| Signal | Production (`run_pipeline`) | Smoke (`run_v1_smoke_pipeline`) |
| --- | --- | --- |
| `expected_document_ids` | `None` → `smoke_mode=False` | tuple provided → `smoke_mode=True` |
| Registration failure | `ValueError` with rejection codes | hard assert via `_assert_registered_package_state` |
| Content resolver | `filesystem_content_resolver` on bundle directory | `None` (fixture-relative reads) |

## Reachable branches in `_run_pipeline_core`

| Location | Condition | Production behavior | Smoke behavior | Evidence class | Disposition |
| --- | --- | --- | --- | --- | --- |
| `content_resolver` | `smoke_mode` | filesystem resolver on `content_root` | no resolver | intentional smoke control | keep smoke; production OK |
| `_pipeline_document_bytes` | `smoke_mode` | `document_store` bytes | `_fixture_bytes` | intentional smoke control | keep smoke; production uses store (tests forbid fixture reads) |
| Secondary XLSX bytes | `smoke_mode` and secondary doc | N/A (uses store path) | substitutes `summit_arc_track_record.xlsx` fixture | intentional smoke control | keep smoke; production uses submitted workbook |
| `_resolve_performance_series` | `smoke_mode` | workbook from registered docs | `_fixture_performance_series()` | intentional smoke control | keep smoke; production path covered by `test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout` |
| `performance["source"]` | `smoke_mode` | `"submitted_workbook"` | `"smoke_fixture"` | prevention assertion | production guarded in CLI tests |
| Scoring block | `not smoke_mode` | `_evidence_backed_score_components` + `gate_scoring_submission` | fixed unavailable explainability; score stays `None` in smoke path | intentional smoke control | production scoring covered by score bundle tests |
| `create_analyst_first_assignment` | always | **fixed** `analyst_001` and `datetime(2026, 3, 4, …)` | same | **confirmed production gap** | return for human/queue owner; link approved queue work (not fixed in this audit PR) |
| Primary extraction service | smoke corpus PDF | legacy pdf fixture service when smoke | same code path if smoke file names used | mixed | production bundles use real submitted bytes; smoke keeps golden corpus |
| `_run_secondary_extraction_boundary_smoke` | secondary workbook | only when secondary is `.xlsx` | boundary smoke with pyodide light | intentional smoke control | production non-workbook secondaries skip boundary (`test_ingest_primary_with_non_workbook_secondary`) |
| In-memory SQLite / `InMemoryDocumentStore` | always | ephemeral stores for CLI run | same | known architectural seam | out of scope (#382 covered readiness); not a smoke-only branch |
| `deck_series` / cross-source comparison | production resolution | `None` (workbook-only today) | fixture may supply deck | **confirmed gap** (Codex review cluster) | return for human; no auto-filed follow-up |
| Remote tracing | `allow_remote_tracing` | disabled from `run_pipeline` | optional in smoke API | intentional | production guarded (`test_ingest_ignores_langsmith_key_when_tracing_disabled`) |

## Linked approved owners (known gaps, no new issues filed)

| Gap | Suggested owner area | Notes |
| --- | --- | --- |
| Fixed analyst queue assignment | queue / validation queue issues | Replace placeholder analyst and clock with operator-driven assignment |
| Cross-source performance comparison unavailable | performance / ingest follow-ups | `deck_series` remains `None` on production workbook path |
| Ephemeral stores in headless CLI | persistence / ops | Documented seam; not introduced by this audit |

## Uncovered items returned for human review

1. **Queue placeholder** — production runs still emit `analyst_001` assignments with a fixed timestamp; confirm target service/API before implementing.
2. **Deck/benchmark comparison** — production path does not populate deck/benchmark series from submitted materials; confirm whether near-term scope exists outside smoke fixtures.

## Prevention coverage

- `tests/cli/test_ingest_entrypoint.py` — production must not call `_fixture_bytes` / `_fixture_performance_series` on the headless path; performance `source` must be `submitted_workbook`.
- `tests/scoring/test_engine.py` — scoring engine invariants (unchanged by this audit).
- `test_run_pipeline_invokes_core_without_smoke_document_ids` (added) — ensures `run_pipeline` never passes `expected_document_ids`, so production cannot enter `smoke_mode` accidentally.
