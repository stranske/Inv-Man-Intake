# Image Feedback Tuning Runbook

## Purpose

This runbook explains how to generate and consume the visual artifact feedback
summary report. The report operationalises human reviewer feedback into metrics
that can inform heuristic adjustments and future model updates.

---

## Generating a Report

### Prerequisites

- A SQLite database containing `visual_artifact_feedback` records (produced by
  the ingestion pipeline via `VisualArtifactFeedbackService`).
- Python environment with `inv_man_intake` on the path (or run from the repo
  root with `src/` in `PYTHONPATH`).

### JSON output (default)

```bash
python scripts/image_feedback_report.py --db /path/to/inv_man.db
```

Write to a file instead of stdout:

```bash
python scripts/image_feedback_report.py \
  --db /path/to/inv_man.db \
  --output reports/feedback_summary.json
```

### CSV output

```bash
python scripts/image_feedback_report.py \
  --db /path/to/inv_man.db \
  --format csv \
  --output reports/feedback_summary.csv
```

### Filtering by time range

Both `--from` and `--to` accept ISO-8601 UTC timestamps. Either bound is
optional.

```bash
python scripts/image_feedback_report.py \
  --db /path/to/inv_man.db \
  --from "2026-01-01T00:00:00Z" \
  --to   "2026-03-31T23:59:59Z"
```

---

## Key Metrics

| Metric | Description |
|--------|-------------|
| `informative_rate` | Fraction of feedback records that mark the artifact as informative (0.0–1.0). |
| `rank_distribution` | Count of feedback records per quality rank (1 = lowest, 5 = highest). |
| `disagreement_rate` | Fraction of unique artifacts where at least two reviewers gave conflicting `is_informative` labels (0.0–1.0). |

---

## Interpreting Results

### Informative rate

- **Above 0.70**: Classifier precision is broadly acceptable; no immediate heuristic change needed.
- **0.50–0.70**: Review the boilerplate-heavy document corpus; consider tightening `boilerplate_terms`.
- **Below 0.50**: Suggests systematic mislabelling; run a sample audit before changing classifier weights.

### Rank distribution

- A healthy distribution has most records at rank 3–5. A spike at rank 1–2
  indicates quality concerns that may require extraction re-tuning.

### Disagreement rate

- **Below 0.15**: Reviewers are broadly aligned; proceed with majority-vote label.
- **0.15–0.30**: Surface the conflicted artifacts to a lead analyst for adjudication.
- **Above 0.30**: Review annotation guidelines; the labelling criteria may be ambiguous.

---

## Scheduling

Run the report on a weekly cadence (e.g. via CI cron or a scheduled agent) and
store the output alongside the date for trend tracking. A sample cron entry for
CI:

```yaml
- name: Generate feedback tuning report
  run: |
    python scripts/image_feedback_report.py \
      --db "${{ env.INV_MAN_DB_PATH }}" \
      --format csv \
      --output reports/feedback_$(date +%Y%m%d).csv
```

---

## Related

- `docs/runbooks/visual_artifact_extraction.md` — extraction pipeline runbook
- `src/inv_man_intake/images/report.py` — aggregation implementation
- `src/inv_man_intake/images/feedback_service.py` — feedback persistence service
- `tests/images/test_feedback_report.py` — aggregation unit tests
