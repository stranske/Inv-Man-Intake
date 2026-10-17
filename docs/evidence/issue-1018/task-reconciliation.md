# Issue #1018 task reconciliation

The prior commits `205e17f` and `d495bc4` implemented the queue handoff and tests but left
all PR checkboxes unchecked. All eleven items below are now verified in this workspace.
The PR body update was rejected because the GitHub tool requires approval and this run
uses approval policy `never`; this file records the verified checklist for handoff.

The follow-up fixes enforce ordered event timestamps within each item's lifetime and
reject ingestion into a directory with saved queue review progress before writing.
The focused regression suite passes (139 tests), including the unchanged smoke transition
test. Suppressing the actual queue artifact write fails all four CLI queue cases;
restoring the source byte-for-byte passes all four. See the adjacent proof and transcripts.

#### Tasks
- [x] Define a versioned queue artifact schema and stable replay key (package_id + escalation reason) in `src/inv_man_intake/workflow_validation.py` (alongside `create_queue_item`) with write and load functions using `ValidationQueueItem` and `QueueEvent`.
- [x] Replace the `create_analyst_first_assignment(... analyst_id="analyst_001" ...)` call at `src/inv_man_intake/v1_smoke.py:379` in production mode with outcome-driven `create_queue_item`, and no item for clean bundles.
- [x] Carry the items through `V1SmokeArtifacts` and write the artifact in `_write_run_artifacts` (`src/inv_man_intake/run.py:349`), adding it to `written` so `build_manifest` hashes it and `artifact_refs` lists it (`src/inv_man_intake/run.py:46`).
- [x] Add CLI tests in `tests/cli/test_ingest_entrypoint.py` for an escalating and a non-escalating bundle: reload the artifact and filter rows by `package_id` via `list_validation_queue`.
- [x] Add replay/idempotency and claim-then-complete tests to `tests/test_validation_queue_api.py` using the existing workflow functions on a reloaded item.
- [x] Update `docs/PRODUCT_CONTRACT.md` IMI-6 row and known-gap note to the verified behavior.

#### Acceptance criteria
- [x] `pytest tests/cli/test_ingest_entrypoint.py -k queue` reloads the artifact and returns expected rows for the escalating bundle and no rows for the no-escalation one.
- [x] The artifact appears in `run.json` `artifact_refs` and `manifest.json` with a matching hash; existing manifest validation accepts it.
- [x] `rg "analyst_001" src/inv_man_intake/run.py src/inv_man_intake/workflow_validation.py` returns nothing and new items are `owner_id=None`.
- [x] A deliberate break suppressing the artifact write fails the CLI queue test; restoring it passes.
- [x] Existing regression coverage must remain passing: `pytest tests/queue/test_v1_smoke_state_transition.py` still passes unchanged.
