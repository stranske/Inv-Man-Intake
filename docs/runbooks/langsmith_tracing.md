# LangSmith Tracing Runbook (Issue #44)

## Goal

Provide reusable tracing wrappers that can be enabled or disabled without changing business logic.

## Core Components

- `TraceContext`: trace ID + parent span + tags
- `Tracer`: starts spans when enabled
- `InMemoryTraceSink`: local sink for tests/dev
- `LangSmithTraceSink`: runtime sink that exports spans through `langsmith.Client`
- `langsmith_fleet`: builds dashboard-safe `langsmith-fleet/v1` records for
  package-level intake, extraction, validation/escalation, and scoring summaries
- `NoopSpan`: safe no-op when tracing is disabled

## Usage Pattern

1. Create root context at workflow entry.
2. Start spans around pipeline stages (`intake`, `extract`, `score`).
3. Derive child contexts with parent span IDs for nested operations.
4. Keep tracing optional so local/offline runs remain functional.

## Example

```python
tracer = Tracer.from_env()
ctx = new_trace_context(tags={"stage": "intake"})

with tracer.start_span(name="ingest", context=ctx, metadata={"package_id": "pkg_1"}):
    pass
```

Decorator-style wrapper (for reusable business-logic functions):

```python
@traced_span(
    tracer=tracer,
    name="extract_positions",
    context=ctx,
    metadata={"provider": "primary"},
)
def extract_positions(payload: dict[str, object]) -> list[dict[str, object]]:
    ...
```

## Toggle Guidance

- Use `enabled=False` for environments without tracing credentials.
- Keep tracing calls in place; no-op mode preserves execution path.

## Environment Setup (LangSmith Keys)

Set the following environment variables before running services that should emit traces:

- `LANGSMITH_API_KEY`: LangSmith API key (required for uploads)
- `LANGSMITH_PROJECT`: project name in LangSmith (recommended)
- `LANGCHAIN_TRACING_V2=true`: enable LangChain/LangSmith tracing
- `INV_MAN_TRACING_ENABLED=true`: enable this repository's tracing wrapper

Example shell setup:

```bash
export LANGSMITH_API_KEY="lsv2_pt_..."
export LANGSMITH_PROJECT="inv-man-intake"
export LANGCHAIN_TRACING_V2="true"
export INV_MAN_TRACING_ENABLED="true"
```

When `LANGSMITH_API_KEY` is present, the repository defaults `LANGSMITH_PROJECT`
and `LANGCHAIN_PROJECT` to `inv-man-intake` and mirrors the key into
`LANGCHAIN_API_KEY` for LangChain-compatible clients. Without a key, tracing
and fleet record creation stay offline-safe and records use status `no_secret`.

## Fleet Dashboard Artifact

Package-level runs can emit `langsmith-fleet.ndjson` records that match the
Workflows-owned `langsmith-fleet/v1` contract for
`stranske/Inv-Man-Intake#438`. Records include shared fields (`repo`, `surface`,
`operation`, `run_id`, `status`, `trace_id`) plus a `domain` block with package,
document, redaction, extraction-count, validation, confidence/escalation, retry,
score, and review queue outcome fields.

The artifact intentionally avoids raw manager documents, source text, extracted
values, prompts, or model outputs. Use stable document/package identifiers,
counts, statuses, trace references, and `artifact:<relative-path>` pointers
instead.

Optional explicit toggle (equivalent behavior):

```bash
export LANGSMITH_TRACING_ENABLED="true"
```

## Reproducible Verification Checklist

1. Confirm env vars are set in the same shell session used to start the app:
   - `env | rg 'LANGSMITH_API_KEY|LANGSMITH_PROJECT|LANGCHAIN_TRACING_V2|INV_MAN_TRACING_ENABLED'`
2. Run setup validator (fails fast if required values are missing/disabled):
   - `python -m inv_man_intake.observability.setup_validation --require-project`
3. Run the probe validator to emit one span through the configured LangSmith client:
   - `python -m inv_man_intake.observability.setup_validation --require-project --probe`
4. Run tracing export tests:
   - `pytest tests/observability/test_langsmith_export.py tests/observability/test_tracing_toggle.py -m "not slow"`
5. Validate disabled mode behavior still works by setting:
   - `INV_MAN_TRACING_ENABLED=false`
6. Validate enabled mode by setting:
   - `INV_MAN_TRACING_ENABLED=true`
   - `LANGCHAIN_TRACING_V2=true`

## Missing Traces Troubleshooting

1. Validate shell env before startup:
   - `env | rg 'LANGSMITH_API_KEY|LANGSMITH_PROJECT|LANGCHAIN_TRACING_V2|INV_MAN_TRACING_ENABLED'`
2. Re-run setup validation with the probe enabled:
   - `python -m inv_man_intake.observability.setup_validation --require-project --probe`
3. Confirm toggles and mocked client export resolve as enabled in tests:
   - `pytest -q tests/observability/test_setup_validation.py tests/observability/test_langsmith_export.py tests/observability/test_langsmith_fleet.py tests/observability/test_tracing_toggle.py --no-cov`
4. Verify application code uses `Tracer.from_env(...)`; local/offline smoke code may still pass an explicit `InMemoryTraceSink`.

## Missing Metrics Troubleshooting

1. Confirm extraction orchestration emits metrics via `metrics_hook`.
2. Run fallback/escalation regression coverage:
   - `pytest -q tests/test_extraction_orchestrator.py --no-cov`
3. Validate observability smoke target locally:
   - `pytest -q tests/observability/test_setup_validation.py tests/observability/test_langsmith_export.py tests/observability/test_tracing_toggle.py --no-cov`
4. If CI passes but runtime metrics are absent, verify runtime logging/metrics sink wiring and deployment env toggles.
