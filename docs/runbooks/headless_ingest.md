# Headless ingest runbook (`inv-man-ingest`)

The `inv-man-ingest` console script runs the full deterministic
intake → extraction → thresholds → performance → queue → scoring path for a
single intake bundle and writes one replayable `run.json` plus three named
artifact files to an operator-supplied output directory. It is the production,
orchestrator-callable counterpart to the `run_v1_smoke_pipeline` test helper;
both delegate to the single core `inv_man_intake.v1_smoke._run_pipeline_core`,
exposed for headless use as `inv_man_intake.run.run_pipeline`.

## Invocation

```bash
# Console script (installed via [project.scripts]):
inv-man-ingest tests/fixtures/intake/pdf_primary_mixed_bundle.json --out ./.run-out

# Equivalent module form:
python -m inv_man_intake.cli.ingest tests/fixtures/intake/pdf_primary_mixed_bundle.json --out ./.run-out
```

- `bundle` (positional): path to the intake bundle JSON file.
- `--out` (required): output directory. Created if missing.

Exit codes: `0` on success, `2` if the bundle file does not exist, `1` if the
bundle is structurally invalid or registration is rejected.

## Output directory layout

All four files are written directly into the supplied `--out` directory:

| File | Contents |
| --- | --- |
| `run.json` | Top-level replayable run record: `run_id`, `inputs`, per-field `fields`, `confidence_state`, `escalation_state`, `final_score`, `explainability`, `warnings`, `latency_ms`, `provenance` (per-field evidence pointers), `trace_refs`, `artifact_refs`. |
| `metadata.json` | Package / firm / fund IDs plus per-document metadata (file name, hash, fund, received-at, source channel). |
| `threshold-summary.json` | The `confidence.document.*` summary fields plus the threshold decision (coverage ratio, auto-pass, escalation reason, auto-accept fields). |
| `explainability.json` | The deterministic `format_explainability_payload` output (per-component weights, contributions, rationale). |

## Data-zone constraint (privacy / LLM boundary)

The deterministic core (intake, `PdfPrimaryExtractionProvider`, thresholds,
scoring) performs **zero network/LLM egress**, so it may be run on real
proprietary packages locally. `run.json` is a *full* per-run artifact that can
carry extracted field values, so it is written **only** to the operator-supplied
`--out` directory and is **never** emitted to the fleet telemetry NDJSON sink
(which enforces its own `SENSITIVE_FIELD_TOKENS` denylist and
`redacted_metadata_only` status). Do not redirect `--out` into a fleet/telemetry
upload path. Any future LLM-backed extraction provider must be gated behind an
authorized no-train endpoint with redaction, or disabled for the proprietary
zone — out of scope for this entry point.
