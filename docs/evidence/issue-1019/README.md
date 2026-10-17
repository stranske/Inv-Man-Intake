# Source #1019 production scoring acceptance

Audited merged revision: `d4aadfe1a16e191b13f83a75fa704fcb02a09053`
(PR #1027; reviewed head `a1f75962accc8b2fd966244694720aeb7ebc32a3`).
The actual comparison run `39059146984` returned CONCERNS/CONCERNS.
Those provider verdicts remain unchanged. This packet supplies independently
observed full-source evidence for their truncation and missing-transcript claims;
the companion scoring contract documents the existing heuristic and minimums.

## Original acceptance evidence

- Numeric production scores for credit and quant, canonical weighting and
  contribution reconciliation: `test_ingest_score_numeric_for_two_supported_asset_classes`.
- Resolvable document/page and workbook pointers in `run.json` and standalone
  explainability: `test_ingest_score_explainability_provenance_is_resolvable`.
- AUM, fee, return, key-person and workbook changes alter the corresponding
  component and aggregate: the five `test_ingest_score_*change*` CLI cases.
- Thin evidence and a nonstandard series retain null scores, the specific
  unavailable reason and `scoring:unavailable`: CLI insufficient-evidence
  and operator-confirmation cases. `run.py` lines 233-237 pass through the
  formatted payload and retain the warning whenever the score is absent.
- Scoring engine, smoke and baseline invariants plus CLI, explainability,
  extraction and smoke-contract suites: **199 passed**; two environment
  warnings about optional pandas acceleration versions, no failed test.
  Exact command and output are in `exact-merged-tests.log` (command below).
- Actual deliberate break: replace the returned evidence-derived tuple in
  `_evidence_backed_score_components` with `_score_components(0.74)`.
  The existing constants and AUM-change regressions both fail (**2 failed**),
  then both pass (**2 passed**) after byte-identical source restoration.
  `causal-proof.json` retains exact command, mutation and restoration hashes;
  raw transcripts are committed beside it. No mutant production change is kept.

```sh
/opt/anaconda3/bin/python3 -m pytest --no-cov -q \
  tests/cli/test_ingest_entrypoint.py tests/scoring/test_engine.py \
  tests/scoring/test_explainability.py tests/test_v1_acceptance_smoke.py \
  tests/baseline/test_invariants.py tests/v1/test_smoke_contract_coverage.py \
  tests/extraction/test_provider_contract.py
```

The full scoring helper, CLI pass-through and all named tests were read locally
at the audited revision. Strict AUM parsing and the full-line extraction change
are covered by the provider and CLI tests; no external enrichment is added.
The old LangSmith artifact regeneration is incidental noise, not a scoring
acceptance failure; this follow-up does not regenerate it. Minimum evidence
and normalization now appear in `docs/contracts/scoring_explainability.md`.

This packet is local acceptance evidence, not a replacement provider PASS or
permission to bypass current-head review, CI, merge and source-verification gates.
