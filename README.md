# Inv-Man-Intake

Inv-Man-Intake is an investment manager package intake pipeline. It tracks a
firm -> fund -> document hierarchy, validates incoming package metadata, routes
low-confidence extraction work to an analyst/ops queue, normalizes performance
inputs, and produces explainable asset-class-specific priority scores.

The v1 design target is documented in
[`docs/INV_MAN_INTAKE_PLAN_V1.md`](docs/INV_MAN_INTAKE_PLAN_V1.md).

## Current Capabilities

- Intake contract validation for PDF, PPTX, XLSX, Word, and email-note package inputs.
- Document registration, versioning, storage, provenance, and correction-history contracts.
- Extraction provider contracts, fallback orchestration, confidence thresholds, and escalation payloads.
- Image artifact extraction primitives for PDF/PPTX visual review.
- Performance normalization, metric calculation, and source-conflict escalation.
- Analyst-first validation queue states, ownership, SLA, audit, and API contracts.
- Configurable scoring weights, score explainability, red-flag hooks, and regression fixtures.
- Observability helpers for tracing, LangSmith export, fleet dashboard records, logging, metrics, and setup validation.

## Headless Backend Contract

Inv-Man-Intake is intentionally a headless intake, scoring, and
validation-queue backend. The repo-local package under `src/` does not ship a
production HTTP/API server such as FastAPI, Gradio, or uvicorn; human review is
expected to happen in a consuming analyst queue rather than in this package.

The consumer UI integration contract for that analyst queue surface is
`src/inv_man_intake/validation_queue_api.py`, which defines filter/query helpers
and paginated queue response contracts for validation rows. A Manager-Database
style analyst queue, or another portfolio operations UI, should integrate
against that contract when it needs to display or triage intake validation work.

The browser demo below is fixture-backed verification evidence for the
deterministic intake path. It lives under `app/`, is demo-only, and is not a
planned production human-facing UI for this repo. The absence of a production
repo-local server in `src/` is a recorded product decision rather than a missing
front-end gap.

## Quick Start

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src/ tests/
mypy
```

### Browser Demo

The synthetic intake demo runs in a local browser as a static SPA with the
vendored Pyodide runtime. Serve it from the repo root so the browser can fetch
the local Pyodide and packet bridge modules; direct `file://` opening is not a
supported verification path. The browser-local bridge routes packet-shaped
uploads through the deterministic packet pipeline when package sources are
available and never sends proprietary payload to LangSmith, an LLM provider, or
an application server.

Live verification gate (no terminal required for reviewer):

1. Run `python -m http.server 8000` from the repo root and open
   `http://127.0.0.1:8000/app/index.html`.
2. Select `pdf_primary_mixed_bundle.json`.
3. Confirm the UI shows `Final score: 0.7809` and a non-empty Explainability
   table.
4. Verification evidence and screenshot are recorded in
   `app/live-verification.md`.

### Deprecated Streamlit/stlite fixture renderer

`app/streamlit_app.py` is a deprecated compatibility renderer for deterministic
fixture tests. It is not a production entrypoint and must not be used for
browser verification or user-facing deployment. Use `app/index.html` and the
static-Pyodide verification path above instead.

The repository uses the shared
[`stranske/Workflows`](https://github.com/stranske/Workflows) CI and agent
automation stack. The local project package is `inv_man_intake`.

## Project Structure

```text
Inv-Man-Intake/
├── config/
│   ├── extraction_thresholds.yaml
│   └── scoring_weights/
├── docs/
│   ├── contracts/
│   ├── runbooks/
│   └── INV_MAN_INTAKE_PLAN_V1.md
├── src/
│   └── inv_man_intake/
│       ├── audit/
│       ├── contracts/
│       ├── data/
│       ├── extraction/
│       ├── images/
│       ├── intake/
│       ├── observability/
│       ├── performance/
│       ├── queue/
│       ├── scoring/
│       └── storage/
└── tests/
```

## Key Commands

```bash
pytest
pytest tests/observability/test_pipeline_smoke.py --no-cov
pytest tests/observability/test_langsmith_fleet.py --no-cov
python -m inv_man_intake.readiness.throughput --output reports/readiness/throughput_readiness.json
ruff check src/ tests/
mypy
```

The throughput readiness command reports a synthetic lower-bound fixture timing. It verifies
that the local smoke path still produces measurable stage timings, but it excludes real
extraction and IO cost and must not be treated as proof of live same-business-day capacity.

LangSmith runtime setup and dashboard artifact fields are documented in
[`docs/runbooks/langsmith_tracing.md`](docs/runbooks/langsmith_tracing.md).

For the current implementation sequence and milestone traceability, see
[`docs/ISSUE_EXECUTION_SEQUENCE.md`](docs/ISSUE_EXECUTION_SEQUENCE.md).
