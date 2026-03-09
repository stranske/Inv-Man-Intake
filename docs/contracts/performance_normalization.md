# Performance Normalization Contract (v1)

## Purpose

Define deterministic normalization behavior for manager-provided performance inputs before
downstream metrics and scoring.

Normalization in v1 does four things:
- Align input dates to period-end boundaries for each supported frequency.
- Produce canonical monthly rows over the observed monthly range.
- Flag missing monthly periods deterministically.
- Provide benchmark alignment hooks for later correlation calculations.

## Input Contract

`normalize_payload(...)` accepts `PerformancePayload`:
- `monthly` (required, frequency must be `"monthly"`).
- `quarterly` (optional, frequency must be `"quarterly"` when present).
- `annual` (optional, frequency must be `"annual"` when present).

Each frequency series must:
- Contain at least one point.
- Be strictly increasing by `as_of`.
- Have no duplicate `as_of` dates.

## Date Canonicalization Rules

All normalized dates are serialized as ISO 8601 calendar dates (`YYYY-MM-DD`).

Frequency-specific period-end alignment:
- `monthly`: snap each point to month-end.
- `quarterly`: snap each point to quarter-end month-end (`03-31`, `06-30`, `09-30`, `12-31`).
- `annual`: snap each point to year-end (`12-31`).

If two points collapse to the same normalized date within a series, normalization fails with a
deterministic validation error.

## Canonical Monthly Output

`normalize_payload(...)` returns `NormalizedPerformancePayload` with:
- Normalized frequency series (`monthly`, `quarterly`, `annual`).
- `canonical_months`: one row per month-end from first normalized monthly point through last.
- `missing_months`: deterministic tuple of month-end dates in range with no monthly value.

Each `canonical_months` row contains:
- `as_of` (month-end date).
- `monthly_value` (`float | None`).
- `quarterly_value` (`float | None`).
- `annual_value` (`float | None`).
- `missing_month` (`bool`).

## Missing-Month Semantics

Gap detection is inclusive over the monthly range:
- Start = first normalized monthly date.
- End = last normalized monthly date.
- Missing = month-end dates in `[start, end]` absent from normalized monthly points.

No interpolation or imputation is performed in v1.

## Benchmark Alignment Hooks

`build_benchmark_alignment(...)` aligns normalized monthly portfolio values with a monthly
benchmark series and emits one of:
- `aligned`.
- `missing_portfolio`.
- `missing_benchmark`.

`correlation_inputs(...)` then extracts aligned `(as_of, portfolio_value, benchmark_value)` triples
for downstream statistics.

v1 intentionally does not compute correlations; it provides stable, ordered inputs only.

## Assumptions

The implementation assumptions are exposed in code by
`describe_normalization_contract()` in `src/inv_man_intake/performance/normalize.py`.

Current assumptions:
- Monthly series is required and defines canonical range boundaries.
- Canonical outputs use ISO 8601 date representation.
- Date normalization snaps to period-end boundaries by frequency.
- Input ordering must already be deterministic and strictly increasing.

## Limitations

Current v1 limitations:
- No source-conflict arbitration across competing provider submissions.
- No interpolation or advanced imputation for missing months.
- No correlation/statistics computation during normalization.
- No support for frequencies outside monthly, quarterly, and annual.

## Determinism Requirements

For identical inputs, normalization must produce identical:
- Normalized dates and values.
- Canonical month row ordering.
- Missing-month flags.
- Benchmark alignment ordering and statuses.
