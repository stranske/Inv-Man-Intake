# Optional workbook selection regression

Source: issue #1017, verifier finding on merged PR #1026 (run 39050456885).

Base: `2cf57809994743f44993378c6ea8446776214c02`.
The old selector chose any secondary when no XLSX was submitted. The production
CLI now ignores DOCX/EML/TXT/MD attachments at its XLSX-only secondary boundary,
keeps primary extraction and document provenance, and reports unavailable
performance without inventing returns. Existing XLSX order/performance tests
remain intact. No intake validation or parser is added.

Run with the shared `/opt/anaconda3/bin/python3`, with
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and pytest `-o addopts=''` (no coverage claim).

- Full regression: `pytest tests/cli/test_ingest_entrypoint.py tests/contracts/test_intake_contract.py tests/test_v1_acceptance_smoke.py`: **70 passed**.
- Focused causal gate: `pytest tests/cli/test_ingest_entrypoint.py -k non_workbook_secondary`: **8 failed** with the original production selector; **8 passed** after byte-identical restoration of the fix.
- Tests are identical across the causal runs. The break replaces only `v1_smoke.py` with its exact base revision. `workbook-causal.json` records the source/test hashes, revision and exit codes; raw logs accompany it.
- Black, Ruff, and MyPy on the changed production module passed locally.

The two warnings in the full run are environment warnings; no whole-repository,
hosted CI, provider PASS or source closure is claimed by this local evidence.
