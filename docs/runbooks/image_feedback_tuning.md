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

Use `--reviewed-from` and `--reviewed-to` with UTC ISO-8601 timestamps to limit the report
window. The JSON summary includes informative rate, quality-rank distribution, reviewer
counts, timestamp range, and disagreement rate. An artifact is counted as a disagreement
when multiple reviewers disagree on informative-vs-boilerplate classification or their
quality ranks differ by two or more points.
