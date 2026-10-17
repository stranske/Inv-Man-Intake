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
