# Throughput Readiness Check

The same-business-day readiness check runs the deterministic v1 fixture package through the local intake-to-scoring smoke path and writes an ephemeral report:

```bash
python -m inv_man_intake.readiness.throughput --output reports/readiness/throughput_readiness.json
```

The fixture runtime is a synthetic lower bound. It excludes real document extraction and IO cost, so it is useful for detecting smoke-path regressions but is not proof of live same-business-day throughput. The command exits `0` only when every required fixture stage produces measurable output and the projected fixture capacity is consistent with the v1 target of 10 to 15 manager packages per week. It exits non-zero when a stage is unavailable, timing evidence is missing, scoring produces no verifiable score, or the fixture batch exceeds the same-business-day target.

The report fields map to the v1 targets:

- `package_count`: number of fixture manager packages processed in this readiness run.
- `stage_timings`: elapsed milliseconds for intake, extraction plus threshold handling, performance normalization, queue/audit output, and scoring.
- `score_count`: count of verifiable scoring outputs produced by the batch.
- `escalation_count`: count of deterministic escalation paths exercised by the fixture batch.
- `projected_packages_per_business_day`: same-day capacity estimate from the observed fixture runtime.
- `synthetic_lower_bound`: always `true` for the default fixture batch, indicating that real extraction and IO cost are excluded.
- `bottleneck_warnings`: concrete caveats or reasons the check is not ready for live testing. The synthetic-lower-bound caveat is non-failing; missing stages, no scores, zero elapsed time, and capacity misses remain failing conditions.

The default output path is ignored by git. Treat it as an operator artifact, not source material.

## Production real-byte batch mode

The smoke report above stays the default (`"mode": "fixture_smoke"`). A separate, measured mode runs a small bundled real-byte corpus (the checked-in conforming Doc-Lineage PDF and XLSX track record from `tests/fixtures/extraction`, staged as two packages) through the production `run_pipeline` entry point, including its output artifact writes:

```bash
python -m inv_man_intake.readiness.throughput --mode production-batch --output reports/readiness/throughput_production_batch.json
```

The report carries `"mode": "production_real_bytes"` and `synthetic_lower_bound: false`. It does not reuse smoke stage timings. Fields:

- `elapsed_seconds`: wall-clock time around the production entry point for the whole batch (staging copies excluded).
- `outcome_counts`: `auto_pass`, `escalated` and `failed` package counts.
- `measured_packages_per_hour` / `measured_packages_per_business_day`: throughput derived from `elapsed_seconds`, not projected from synthetic spans.
- `production_extractor_verified` / `extraction_methods`: derived from emitted field methods (`doc-lineage:*`), proving the production extractor ran rather than the legacy fixture parser.
- `verified_outputs`: every artifact listed in each `run.json` plus `manifest.json` exists and is non-empty.

The command requires the `extraction-doc-lineage` extra; a missing or broken install raises instead of falling back. The corpus is tiny, so treat the figure as a measured floor for per-package overhead on small inputs, not a capacity guarantee for large real packages.
