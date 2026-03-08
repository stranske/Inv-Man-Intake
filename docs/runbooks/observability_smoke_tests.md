# Observability Smoke Tests Runbook (Issue #46)

## Goal

Provide fast smoke coverage for extraction tracing and fallback/escalation metrics behavior.

## What Is Covered

- Tracing-enabled extraction path keeps one correlation trace/run identity across run stages.
- Tracing-disabled path runs with no emitted trace events.
- Fallback success and escalation paths both update metrics counters through the orchestrator hook.

## Test Target

Run the dedicated observability smoke target:

```bash
pytest -q tests/observability/test_pipeline_smoke.py --no-cov
```

Run all observability tests:

```bash
pytest -q tests/observability --no-cov
```

## CI Compatibility Notes

- The smoke suite is a standard pytest target under `tests/observability/`.
- Existing reusable Python CI and Gate workflows execute pytest, so no extra required CI stage is introduced.
- This keeps compatibility with the current Workflows baseline while adding observability regression coverage.

## Troubleshooting

### Missing trace events in enabled-mode smoke test

- Confirm `Tracer(enabled=True, sink=...)` is used.
- Ensure the same `trace_context` object is passed to orchestrator `.run(...)`.

### Unexpected trace events in disabled-mode smoke test

- Confirm `Tracer(enabled=False, sink=...)` is configured.
- Verify no alternate tracer instance is injected during test setup.

### Counters do not increment as expected

- Check `metrics_hook` wiring in orchestrator construction.
- Validate assertions against payload fields: `resolved`, `retry_count`, `failure_count`.
