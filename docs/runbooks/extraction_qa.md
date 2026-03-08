# Extraction QA Runbook

This runbook defines how to execute and interpret extraction QA corpus regression checks.

## QA Corpus

- Fixture corpus path: `tests/fixtures/extraction/qa_corpus.json`
- Current fixture scenarios:
- dense table manager report
- scan-style OCR noise sample
- mixed layout slide sample
- Expected outputs are stored per fixture in the `expected_fields` map.

## Generate Baseline Quality Report

Run the report script from repository root:

```bash
python scripts/extraction_quality_report.py
```

Optional output file:

```bash
python scripts/extraction_quality_report.py --output artifacts/extraction_quality_report.json
```

The report includes:
- `accuracy`: correct extracted values among extracted expected keys
- `completeness`: correct extracted values among all expected keys
- `parser_failure_count`: fixtures that raised provider exceptions
- `fallback_usage_count`: fixtures resolved by non-primary provider

## Regression Test Procedure

Run targeted QA regression tests:

```bash
pytest -q tests/extraction/test_quality_regression.py
```

If thresholds fail:
1. Inspect fixture-level `missing_keys` and `incorrect_values` from the report output.
2. Confirm whether failures are parser regressions or fixture expectation drift.
3. Update extraction patterns or fixture expectations with a linked issue/PR note.
4. Re-run the report and regression test until metrics recover.
