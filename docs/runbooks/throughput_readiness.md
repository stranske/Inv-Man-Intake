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

To obtain a realistic live capacity figure, run a real-cost batch after the real-bytes intake path and production extractor are available. That follow-up should time the same stage boundaries against real package bytes instead of the deterministic fixture-only smoke path.
