# Performance Normalization Contract (v1)

## Purpose

Define deterministic normalization behavior for manager performance inputs before metrics/scoring.

This stage:
- Aligns dates to frequency period-end boundaries.
- Builds canonical month rows for downstream processing.
- Flags missing months in the observed monthly range.
- Provides benchmark alignment hooks for later correlation calculations.

## Inputs

- `PerformancePayload` from `inv_man_intake.performance.ingest`:
  - `monthly` (required)
  - `quarterly` (optional)
  - `annual` (optional)

## Date Normalization Rules

- `monthly`: normalize each point to month-end.
- `quarterly`: normalize each point to quarter-end month-end (`03-31`, `06-30`, `09-30`, `12-31`).
- `annual`: normalize each point to year-end (`12-31`).

If two input points collapse into the same normalized period for a frequency, normalization fails with a deterministic validation error.

## Canonical Monthly Output

`normalize_payload(...)` returns `NormalizedPerformancePayload` with:
- normalized frequency series (`monthly`, `quarterly`, `annual`)
- `canonical_months`: month-by-month rows from first normalized monthly point through last normalized monthly point
- `missing_months`: deterministic tuple of missing month-end dates in that range

`canonical_months` rows include:
- `as_of`
- `monthly_value` (nullable)
- `quarterly_value` (nullable)
- `annual_value` (nullable)
- `missing_month` (boolean)

## Missing-Month Detection

Gap detection is deterministic and inclusive over the monthly range:
- start = first normalized monthly date
- end = last normalized monthly date
- missing = month-end dates in `[start, end]` that have no monthly value

No interpolation or imputation is performed in v1.

## Benchmark Alignment Hook

`build_benchmark_alignment(...)` aligns normalized portfolio monthly values against a benchmark monthly series and emits:
- `aligned` (both values present)
- `missing_portfolio` (benchmark only)
- `missing_benchmark` (portfolio only)

`correlation_inputs(...)` extracts aligned month/value triples for downstream correlation logic.

This intentionally stops short of computing correlation metrics; it provides stable aligned inputs only.

## Determinism Expectations

For identical payload inputs:
- normalized period dates are identical,
- canonical month row ordering is identical,
- missing month flags are identical,
- benchmark alignment status ordering is identical.

## v1 Limitations

- No source conflict arbitration (handled in separate workstream).
- No return interpolation or advanced gap imputation.
- No correlation/statistics computation in this stage.
