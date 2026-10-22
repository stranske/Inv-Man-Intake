# Product contract — stranske/Inv-Man-Intake
_First draft generated 2026-09-20 from the audit scorecard; the repo owns this file from now on. A PR that adds a user-facing route, command or page adds a line here. The audit's Phase 1.5 scores every line below and prints any surface not listed as UNSCORED._

## Purpose
Register manager document packages, extract provenance-backed fields, apply thresholds, and produce analyst scoring and queue artifacts.

## Primary journey
Submit bundle → register and extract fields → evaluate thresholds → normalize workbook performance → score and explain → review queue → export artifacts.

## Core functions
| id | a user can … and sees … | entry point | probe (how to exercise it; vary these determinants) | status 2026-09-20 |
|---|---|---|---|---|
| IMI-1 | an analyst can ingest a document package and sees a registered run with document IDs and artifacts | `inv-man-ingest <bundle.json> --out <dir>` | vary Alpha/Beta and invalid required metadata, received_at, filename/extension and primary-document cases; compare errors/run IDs | WORKS |
| IMI-2 | an analyst can extract fields and sees page pointer, snippet and confidence | pipeline / `PdfPrimaryExtractionProvider` | process Alpha vs Beta PDFs; compare asset class, AUM, returns and source pages | WORKS |
| IMI-3 | an analyst can apply thresholds and sees escalation reason and threshold summary | `v1_smoke._run_pipeline_core` thresholds | run bundles with differing fields; inspect coverage and escalation | WORKS |
| IMI-4 | an analyst can normalize workbook performance and sees submitted-file decimal returns and metrics | bundle `performance_track_record` XLSX | ingest different Alpha/Beta returns workbooks; compare series and source | WORKS |
| IMI-5 | an analyst can compute priority score and sees numeric score with evidence-backed components | scoring stage → `final_score`, `explainability.json` | run production Alpha/Beta bundles; compare against smoke demo score | WORKS |
| IMI-6 | an analyst can reload the local CLI queue handoff and review filterable paginated rows | `workflow_validation.load_validation_queue_rows`, `validation_queue_api.list_validation_queue` | run CLI queue regressions; reload records/events, filter package IDs, claim and complete | IMPLEMENTED (local artifact) |
| IMI-7 | an analyst can export a run and sees named metadata, threshold and explainability artifacts | `--out` directory | ingest Alpha/Beta bundles; compare four emitted artifact files | WORKS |

## Known gaps at draft time
- IMI-5: production runs derive the five components from extracted fields (asset class, fee, 1Y return, AUM, key-person risk) and submitted-workbook metrics via `_evidence_backed_score_components`, score with `weights_for_registry()`, and emit provenance-backed explainability; below minimum evidence they emit `final_score: None` with `evidence_backed_score_components_unavailable` / `scoring:unavailable`. Smoke headline `0.7809` remains a fixture-only demo.
- IMI-6 emits `validation-queue.json` (`validation-queue/v1`) on every production run, registered and hashed in the manifest. Threshold/extraction escalations create unowned pending items with stable package/reason IDs and UTC timestamps; accepted bundles emit an empty queue. Reloading preserves workflow events and ownership. This is a local handoff, not a queue database or hosted service.
