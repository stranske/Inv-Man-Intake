# Image Feedback Tuning Report

Visual artifact feedback can be exported as a tuning report after
`visual_artifact_feedback` has been populated by reviewer workflows.

Generate JSON:

```bash
python scripts/image_feedback_report.py --database path/to/intake.sqlite --format json --output reports/image-feedback.json
```

Generate artifact-level CSV:

```bash
python scripts/image_feedback_report.py --database path/to/intake.sqlite --format csv --output reports/image-feedback.csv
```

Generate a schedule/manual bundle (JSON + CSV in one run):

```bash
python scripts/image_feedback_report.py --database path/to/intake.sqlite --bundle-dir reports/image-feedback/
```

This creates timestamped files (`image-feedback-<generated_at>.json` and
`image-feedback-<generated_at>.csv`) suitable for cron or nightly job archives.

Use `--reviewed-from` and `--reviewed-to` with UTC ISO-8601 timestamps to limit the report
window. The JSON summary includes informative rate, quality-rank distribution, reviewer
counts, timestamp range, and disagreement rate. An artifact is counted as a disagreement
when multiple reviewers disagree on informative-vs-boilerplate classification or their
quality ranks differ by two or more points.

## Interpretation guidance for tuning decisions

Use a minimum sample-size guard before acting on metrics. As a default baseline, require
at least 30 feedback records and at least 10 multi-reviewer artifacts in the selected window.
If volume is lower, continue collecting feedback before changing extraction heuristics.

Interpret `informative_rate` as recall pressure for extraction and ranking quality:

- Rising informative rate with stable disagreement rate indicates the current extraction profile
  is surfacing useful artifacts consistently.
- Falling informative rate suggests the pipeline is surfacing more boilerplate than signal.
  Prioritize threshold and filtering adjustments for source types with the lowest artifact-level
  informative fractions.

Interpret `quality_rank_distribution` as severity and prioritization signal:

- A shift toward ranks 1-2 indicates quality regressions. Review the affected artifacts and
  tune extraction thresholds or source-specific normalization first.
- Concentration at rank 3 suggests marginal quality where small prompt or weighting updates may
  produce gains.
- Growth in ranks 4-5 indicates changes are likely improving practical usefulness.

Interpret `disagreement_rate` as rubric clarity and reviewer calibration signal:

- High disagreement rate (for example >0.30 over a stable sample) means either rubric ambiguity
  or unstable model behavior. Run reviewer calibration and inspect disagreement artifacts before
  model updates.
- Low disagreement rate with low informative rate indicates reviewers agree the output is weak,
  which is a stronger signal to prioritize heuristic/model tuning.

Recommended tuning loop:

1. Generate a bounded-window report (`--reviewed-from/--reviewed-to`) and archive JSON+CSV.
2. Identify the worst-performing segment from artifact-level rows (low informative fraction,
   low average quality rank, high disagreement flag).
3. Apply one focused change (threshold, extraction prompt, ranking weight, or model version).
4. Re-run the report on the next comparable window and compare informative rate,
   rank distribution, and disagreement rate before rolling out broadly.
