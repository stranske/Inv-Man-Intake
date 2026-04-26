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
- Observability helpers for tracing, logging, metrics, and setup validation.

## Quick Start

```bash
python -m pip install -e ".[dev]"
pytest
ruff check src/ tests/
mypy
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
ruff check src/ tests/
mypy
```

For the current implementation sequence and milestone traceability, see
[`docs/ISSUE_EXECUTION_SEQUENCE.md`](docs/ISSUE_EXECUTION_SEQUENCE.md).
