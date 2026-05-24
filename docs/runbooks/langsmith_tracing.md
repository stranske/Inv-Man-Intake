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
`operation`, `run_id`, `status`, `trace_id`, optional `latency_ms`, top-level
`error_category`) plus a `domain` block with package, document, redaction,
extraction-count, validation, confidence/escalation, retry, score, and review
queue outcome fields.

The artifact intentionally avoids raw manager documents, source text, extracted
values, prompts, or model outputs. Use stable document/package identifiers,
counts, statuses, trace references, and `artifact:<relative-path>` pointers
instead.

### Contract validation (local subset)

`langsmith_fleet.write_fleet_records` invokes `validate_fleet_records` before
writing NDJSON so the artifact cannot leave the runner with malformed,
sensitive-payload-bearing, or unsafe-artifact-reference records. The validator
enforces this subset of the Workflows fleet contract:

- Required top-level fields: `schema_version`, `repo`, `surface`, `operation`,
  `run_id`, `status`, `github_issue`, `recorded_at`, `domain`, `error_category`.
  `schema_version`, `repo`, and `surface` must equal the repo-specific
  constants; `status` must be one of `success`, `error`, `fallback`,
  `no_secret`, `skipped`.
- Required domain fields: `package_id`, `correlation_id`, `document_count`,
  `document_ids`, `document_types`, `redaction_status`, `trace_refs`,
  `validation_status`.
- `artifact_ref` (top-level) and `artifact_refs` / `report_artifacts` (in
  `domain`) must use safe `artifact:<relative-posix-path>` references — no
  absolute paths, no drive-letter prefixes, no `..` segments, no backslashes.
- No field anywhere in a record may have a name matching sensitive payload
  tokens (e.g., `document_text`, `extracted_value`, `model_output`, `api_key`,
  `pii`, `ssn`).

### Artifact correlation

Pair each LangSmith trace with operator-facing artifacts by emitting records
whose `artifact_ref` (and `domain.artifact_refs` for the package-intake stage)
point at the workflow artifacts an operator can download from the run summary:
the package metadata snapshot, threshold/explainability artifacts, and the
fleet NDJSON itself. `trace_refs` in `domain` then link the same record back to
the LangSmith trace via `trace:<trace_id>` references, so operators can hop
from a verifier report or dashboard row to the trace and back to the supporting
artifact without seeing redacted content.

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
