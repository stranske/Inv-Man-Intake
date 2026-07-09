# Docling field-accuracy benchmark

This benchmark evaluates `DoclingPrimaryExtractionProvider` against a small
rotating corpus of committed fixture documents. It is intended to catch provider
contract and field-mapping regressions without depending on private Drive
material or live user documents.

## Sample selection

The initial corpus uses four representative samples already present in the
repository, plus one text fixture derived from the checked-in QA corpus:

- `summit_arc_investment_update.pdf`: text-bearing PDF bytes.
- `harborline_strategy_review.pptx`: presentation text runs.
- `tests/fixtures/extraction/sample_manager_package.txt`: simple manager package text.
- `fixtures/docling_samples/qa_dense_table_manager_report.txt`: dense table-style text
  copied from `tests/fixtures/extraction/qa_corpus.json`.

Rotate the sample with either `--sample-index` or the
`IMI_DOCLING_EVAL_SAMPLE_INDEX` environment variable. Use `--all` for a full
corpus pass.

## Expected results schema

`fixtures/docling_samples/expected_results.json` is keyed by sample id. Each
sample entry contains:

- `source_path`: repository-relative sample path.
- `description`: short human-readable sample purpose.
- `expected_fields`: flat mapping from canonical extraction field name to exact
  expected string value.

Each `expected_fields` key must match the canonical provider field key, for
example `terms.management_fee` or `strategy.name`. Values are exact expected
strings after normal whitespace and case normalization by the shared
field-accuracy evaluator.

## Structured-output decision

This issue does not require an LLM structured-output layer such as `instructor`
or `outlines`. The Docling provider is a document-text extraction adapter; it
uses Docling for text/table/image modalities and the existing canonical regex
field extractor for deterministic field mapping. If a later LLM-assisted
extraction path is introduced, that path should add a separate optional extra,
schema-valid tests, and benchmark expectations instead of making Docling itself
depend on an LLM runtime.

## Running

```bash
PYTHONPATH=src python eval/benchmarks/docling_field_accuracy.py --sample-index 0
PYTHONPATH=src python eval/benchmarks/docling_field_accuracy.py --all
```

The harness prints a metric named `field_accuracy`:

```text
field_accuracy: 0.80
```
