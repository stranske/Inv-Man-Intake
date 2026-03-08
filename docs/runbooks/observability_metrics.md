# Observability metrics and logging runbook

This runbook defines the v1 operational logging and counters introduced for issue #45.

## Structured log fields

Required fields on each emitted record:

- `correlation_id`: stable request id propagated across intake/extraction/scoring.
- `stage`: pipeline stage (`intake`, `extraction`, `scoring`, etc.).
- `status`: lifecycle status (`success`, `failed`, `fallback`, `escalated`).
- `error_code`: machine-readable error identifier when status is not successful.

Recommended optional fields:

- `message` for human-readable context.
- retry/accounting fields such as `retry_count`, `document_id`, `fund_id`.

## Core metric definitions

- `pipeline_failure_total` counter:
  - tags: `stage`, `error_code`
  - increments whenever a stage exits with failure.
- `pipeline_fallback_total` counter:
  - tags: `stage`, `reason`
  - increments when fallback provider/path is selected.
- `pipeline_escalation_total` counter:
  - tags: `stage`, `reason`
  - increments when manual analyst/ops escalation is triggered.
- `pipeline_latency_ms` timer:
  - tags: `stage`, `status`
  - observed latency in milliseconds for each stage completion.

## Baseline threshold guidance

- Failures: investigate if any stage failure rate exceeds 2% over rolling 24h.
- Fallbacks: investigate provider quality if fallback rate exceeds 10%.
- Escalations: investigate workflow quality if escalation rate exceeds 3%.
- Latency: investigate queueing/provider performance when p95 exceeds 2000ms.

## Validation command

Run:

`pytest -q tests/observability/test_logging_metrics.py --no-cov`
