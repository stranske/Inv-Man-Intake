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

## Toggle Guidance

- Use `enabled=False` for environments without tracing credentials.
- Keep tracing calls in place; no-op mode preserves execution path.
