# Scoring Explainability Contract

Issue: #38  
Parent workstream: #13

This contract defines deterministic explainability payloads for scoring outputs.

## Payload Schema

Top-level fields:

- `overall_score` (`float`): final score value.
- `total_contribution` (`float`): sum of component contributions.
- `components` (`array`): sorted component-level explanation rows.

Each component object includes:

- `component` (`string`): stable component identifier.
- `weight` (`float`): component weight used in scoring.
- `contribution` (`float`): `weight * score` rounded to 6 decimals.
- `rationale` (`string`): concise explanation for the component effect.
- `provenance` (`array`): resolvable source pointers for the component. Each
  entry has `source_kind` (`document`, `workbook`, or `analyst`), `reference`
  (extracted field key, workbook file name, or analyst id), `source_doc_id`
  (document id in the run's `inputs.document_ids`, or `null`), and
  `source_page` (1-based page for `document` entries, otherwise `null`).
  `document` entries resolve against `run.json` `provenance.evidence` by
  `reference`: `source_doc_id` and `source_page` must match that field's
  evidence. Production components carry document/workbook provenance;
  smoke-only components carry analyst provenance. The builder rejects
  unknown `source_kind` values, `document` entries without a document id or
  1-based page, and `workbook`/`analyst` entries carrying a page.

## Determinism Rules

- Components are sorted by `component` identifier before output.
- Numeric values are rounded to 6 decimals.
- Formatting is stable for repeated calls with identical payload input.

## Reconciliation Rules

- `total_contribution` is the exact sum of formatted component contributions.
- If `overall_score` is supplied by caller, it must reconcile to component total
  within tolerance (`1e-6`), otherwise reject with deterministic error.
- If `overall_score` is omitted, it defaults to `total_contribution`.


## Production evidence thresholds and normalization (issue #1019)

The production mapping is `_evidence_backed_score_components` in
`src/inv_man_intake/v1_smoke.py`. These rules describe the current deterministic
heuristic; they are not an empirically calibrated investment recommendation.
Canonical asset-class registry weights and scoring red-flag rules still apply.
The fixture-only `_score_components` values remain restricted to smoke mode.

A production score requires all of the following:

- All five fields (`strategy.asset_class`, `terms.management_fee`,
  `performance.net_return_1y`, `operations.aum`, `team.key_person_risk`) have
  nonblank values, extraction confidence **at least 0.50**, a source document
  ID and a source page. The explainability builder requires document pages
  to be 1-based. Production constructs pointers from extracted fields; the CLI
  regression checks their resolution against the extracted evidence. The builder
  validates pointer structure, not membership in an external evidence registry.
- The submitted workbook supplies **at least three monthly observations** and
  non-null annualized volatility, maximum drawdown and Sharpe ratio. Sortino
  is optional. Fixture returns and invented benchmarks do not fill gaps.
- The asset class normalizes through the canonical registry; management fee
  and one-year net return parse as percentages; AUM parses to one unambiguous,
  strictly positive amount. AUM supports thousand/million/billion units and
  their implemented abbreviations, or a complete unitless numeric amount;
  multiple candidate amounts are unavailable rather than guessed.
- The production `ScoreSubmission` passes `gate_scoring_submission`. A series
  requiring operator confirmation remains unavailable until that existing
  gate is satisfied.

Let `clamp(x) = max(0, min(1, x))`. Percent inputs use decimal fractions
(1.25% = 0.0125). Components are rounded to six decimals before canonical
weighting:

| Component | Current deterministic calculation |
| --- | --- |
| `performance_consistency` | `clamp(0.6 * (1 - annualized_volatility) + 0.4 * (1 - min(max_drawdown * 4, 1)))` |
| `risk_adjusted_returns` | `clamp(0.8 * clamp(0.5 + sharpe_like / 4) + 0.2 * clamp(0.5 + net_return_1y / 0.20))`, where `sharpe_like` is Sharpe alone, or the mean of Sharpe and Sortino when Sortino exists |
| `operational_quality` | `clamp(0.6 * clamp((log10(aum) - 6) / 4) + 0.4 * clamp(1 - management_fee / 0.03))`; AUM spans 1 million to 10 billion before clamping, and fee spans 0% to 3% |
| `transparency` | Clamped mean confidence of the five required extracted fields |
| `team_experience` | Departure/pending/leaving/resigned wording: 0.35; otherwise the word `high`: 0.40; moderate/medium: 0.60; reassuring no-key-person/low-risk/stable-team/none wording: 0.90; fallback: 0.65. Explicitly negated departure phrases are removed before adverse matching; another adverse mention still wins. |

Below the evidence minimum, `final_score` stays null, explainability names
`evidence_backed_score_components_unavailable`, and the CLI retains its
`scoring:unavailable` warning. The operator gate instead names
`operator_confirmation_required` and also retains the warning. Available
scores carry document/workbook provenance and reconcile component
contributions to the final score under the rules above. Smoke analyst
provenance is not a substitute for production source evidence.
