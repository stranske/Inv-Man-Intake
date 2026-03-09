# LangSmith Tracing Runbook (Issue #44)

## Goal

Provide reusable tracing wrappers that can be enabled or disabled without changing business logic.

## Core Components

- `TraceContext`: trace ID + parent span + tags
- `Tracer`: starts spans when enabled
- `InMemoryTraceSink`: local sink for tests/dev
- `NoopSpan`: safe no-op when tracing is disabled

## Usage Pattern

1. Create root context at workflow entry.
2. Start spans around pipeline stages (`intake`, `extract`, `score`).
3. Derive child contexts with parent span IDs for nested operations.
4. Keep tracing optional so local/offline runs remain functional.

## Example

```python
sink = InMemoryTraceSink()
tracer = Tracer(enabled=True, sink=sink)
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
export LANGSMITH_PROJECT="inv-man-intake-dev"
export LANGCHAIN_TRACING_V2="true"
export INV_MAN_TRACING_ENABLED="true"
```

Optional explicit toggle (equivalent behavior):

```bash
export LANGSMITH_TRACING_ENABLED="true"
```

## Reproducible Verification Checklist

1. Confirm env vars are set in the same shell session used to start the app:
   - `env | rg 'LANGSMITH_API_KEY|LANGSMITH_PROJECT|LANGCHAIN_TRACING_V2|INV_MAN_TRACING_ENABLED'`
2. Run setup validator (fails fast if required values are missing/disabled):
   - `python -m inv_man_intake.observability.setup_validation --require-project`
3. Run tracing tests:
   - `pytest tests/observability/test_tracing_toggle.py -m "not slow"`
4. Validate disabled mode behavior still works by setting:
   - `INV_MAN_TRACING_ENABLED=false`
5. Validate enabled mode by setting:
   - `INV_MAN_TRACING_ENABLED=true`
   - `LANGCHAIN_TRACING_V2=true`
