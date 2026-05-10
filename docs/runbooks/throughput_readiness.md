# Throughput Readiness Check

The same-business-day readiness check runs the deterministic v1 fixture package through the local intake-to-scoring smoke path and writes an ephemeral report:

```bash
python -m inv_man_intake.readiness.throughput --output reports/readiness/throughput_readiness.json
```

The command exits `0` only when every required stage produces measurable output and the projected same-day fixture capacity is consistent with the v1 target of 10 to 15 manager packages per week. It exits non-zero when a stage is unavailable, timing evidence is missing, scoring produces no verifiable score, or the fixture batch exceeds the same-business-day target.

The report fields map to the v1 targets:

- `package_count`: number of fixture manager packages processed in this readiness run.
- `stage_timings`: elapsed milliseconds for intake, extraction plus threshold handling, performance normalization, queue/audit output, and scoring.
- `score_count`: count of verifiable scoring outputs produced by the batch.
- `escalation_count`: count of deterministic escalation paths exercised by the fixture batch.
- `projected_packages_per_business_day`: same-day capacity estimate from the observed fixture runtime.
- `bottleneck_warnings`: concrete reasons the check is not ready for live testing.

The default output path is ignored by git. Treat it as an operator artifact, not source material.
