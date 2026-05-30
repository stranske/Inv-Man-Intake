# Inv-Man-Intake workloop state

## 2026-05-30T06:12Z - opener (codex) materializing issue #470

- **Lane:** opener (Codex), automation `pd-workloop-resume`.
- **Issue:** stranske/Inv-Man-Intake#470 - Implement a durable DocumentStore and run the intake persistence path off in-memory/ephemeral storage.
- **Branch:** `codex/issue-470-durable-document-store`.
- **Change:** added `FilesystemDocumentStore`, `register_intake_bundle_to_path(...)`, durable reload/idempotency tests, and runbook documentation for on-disk SQLite + filesystem document storage.
- **Validation:** `python -m pytest tests/storage/test_durable_document_store.py tests/intake/test_versioning.py tests/test_v1_acceptance_smoke.py::test_v1_acceptance_smoke_exercises_intake_to_scoring_path --no-cov`; `python -m ruff check ...`; `python -m ruff format --check ...`; `python -m mypy src/inv_man_intake`; `git diff --check`.
- **Next:** push branch, open ready-for-review PR with `agent:codex`, `agents:keepalive`, and `autofix`.
