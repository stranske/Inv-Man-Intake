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

## Quick Start

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src/ tests/
mypy
```

### Browser Demo

The synthetic intake demo can run in a local browser through `app/index.html`
with stlite/Pyodide. It uses the committed Summit Arc fixture bundles in
`tests/fixtures/intake/`, disables `LANGSMITH_API_KEY`, and executes the same
deterministic `run_v1_smoke_pipeline` path locally so no proprietary payload is
sent to LangSmith, an LLM provider, or an application server. The pinned stlite
runtime version is tracked in `requirements-stlite.lock`.

Live verification gate (no terminal required for reviewer):

1. Open `app/index.html` directly in a browser, or open
   `http://127.0.0.1:8000/app/index.html` after running
   `python -m http.server 8000` from the repo root.
2. Select `pdf_primary_mixed_bundle.json`.
3. Confirm the UI shows `Final score: 0.7809` and a non-empty Explainability
   table.
4. Verification evidence and screenshot are recorded in
   `app/live-verification.md`.

For developer iteration, install the optional app dependency and run:

```bash
python -m pip install -e ".[app]"
streamlit run app/streamlit_app.py
```

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
