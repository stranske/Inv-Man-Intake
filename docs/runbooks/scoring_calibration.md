# Scoring Calibration Runbook

This runbook defines the release-time workflow for scoring regression and calibration checks.

## Inputs

- Baseline fixture snapshot: `tests/fixtures/scoring/launch_asset_class_scores.json`
- Candidate scoring snapshot produced from the branch under review

Both JSON files must contain a list of records in the format:

```json
{"manager_id":"<id>","asset_class":"<class>","score":0.0}
```

## Run Calibration

Generate a report from fixtures only:

```bash
python scripts/scoring_calibration_report.py
```

Generate a report comparing a branch snapshot to the baseline:

```bash
python scripts/scoring_calibration_report.py \
  --baseline tests/fixtures/scoring/launch_asset_class_scores.json \
  --candidate /tmp/current_scores.json \
  --max-score-delta 0.05 \
  --max-rank-movement 1 \
  --output /tmp/scoring-calibration-report.md
```

## Alert Policy

- `score_delta` alert: absolute score change is greater than `--max-score-delta`.
- `rank_movement` alert: ranking movement within an asset class is greater than
  `--max-rank-movement`.

Default thresholds are:

- Max score delta: `0.05`
- Max rank movement: `1`

Tune thresholds for release sensitivity, but keep changes documented in PR validation notes.

## Release Checklist

1. Confirm fixture coverage includes all launch asset classes.
2. Run `pytest tests/scoring/test_regression_rankings.py`.
3. Run calibration report script with candidate snapshot.
4. If alerts are present, document rationale or block release pending review.
