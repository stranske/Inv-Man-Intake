## 2026-06-10T23:10Z - opener (codex) issue #547 directional baseline PR

- Lane: opener / new_issue. Materialized approved weekly-review queue item as issue **#547** (`Add directional baseline checks for 4 non-RAR scoring contribution metric keys`) and implemented branch `codex/issue-547-directional-baselines`.
- Worktree: `/Users/teacher/.codex/automations/pd-workloop-resume/worktrees/inv-man-547-directional`.
- Implementation: added four isolated `set_component` baseline scenarios and enforced directional checks for `contribution.performance_consistency`, `contribution.operational_quality`, `contribution.transparency`, and `contribution.team_experience`; expanded priority coverage to all produced flat metric keys; regenerated `docs/reports/baseline-coverage.md`.
- Validation: `pytest tests/baseline/test_directional.py --no-cov` (12 passed); focused new checks with `-k "raise_performance_consistency_contribution or raise_operational_quality_contribution or raise_transparency_contribution or raise_team_experience_contribution"` (4 passed); `pytest tests/baseline/test_coverage_manifest.py::test_catalog_contract_shape --no-cov` (passed); `BASELINE_REFRESH_REPORT=1 pytest tests/baseline/test_coverage_manifest.py::test_emit_coverage_report --no-cov` (passed); final `pytest tests/baseline/test_directional.py tests/baseline/test_coverage_manifest.py --no-cov` (16 passed).
- Deliberate-break gate: temporarily changed `raise_performance_consistency_contribution` to `direction: decrease`; quoted pytest node id failed with `Economically wrong direction -- ... variant=0.24 decrease control=0.18 -> False`; restored `increase` and reran green.
- Extra disposition: stale approved TPP queue item was materialized as `Travel-Plan-Permission#1182`, then closed as duplicate/completed because the same work already merged via `Travel-Plan-Permission#1179` / PR `#1180` at `2026-06-10T18:23:16Z` (`b9be2d7` on main).
- PR state: PR **#548** is open/non-draft, closes #547, head `4b2a8b6`, labels [agent:codex, agents:keepalive, autofix, repo-review-approved, priority:normal]. Direct PR status immediately after open showed Gate/Agents Gate Followups/CI/guard jobs queued or in progress; cap-health lagged with `needs-dispatch-evidence`, but direct checks showed active async worker evidence.
- Next action: keepalive/Gate owns PR #548.

## 2026-06-03T16:08:45Z - opener (codex) issue #518 -> PR #519

- Lane: opener / new_issue. Materialized approved weekly-review queue item as issue **#518** (`Wire load_threshold_config() from config/extraction_thresholds.yaml into the headless ingest production path`) and opened ready-for-review PR **#519**.
- Branch/worktree: `codex/issue-518-threshold-config` in the automation worktree for issue #518.
- Implementation: `run_pipeline()` now loads the repo-bundled `config/extraction_thresholds.yaml` by default, threads the resulting threshold config into `_run_pipeline_core()`, and `inv-man-ingest` accepts `--threshold-config PATH`. The smoke core keeps its existing one-field fallback when no config is supplied. `docs/contracts/extraction_thresholds.md` now states that production headless runs load the YAML by default.
- Regression coverage: added `tests/run/test_pipeline_threshold_config.py` to assert the committed YAML mandatory-field set and to prove a custom YAML config changes the generated `threshold-summary.json` escalation reason to `confidence_below_threshold:operations.aum`.
- Deliberate-break gate: temporarily removed the `threshold_config=threshold_config` pass-through in `run_pipeline()`; `python -m pytest tests/run/test_pipeline_threshold_config.py::test_run_pipeline_uses_yaml_mandatory_fields -q --no-cov` failed on `low_key_field_coverage` versus `confidence_below_threshold:operations.aum`; restored and reran green.
- Validation: `python -m pytest tests/run/test_pipeline_threshold_config.py tests/run/test_manifest.py tests/cli/test_ingest_entrypoint.py tests/extraction/test_thresholds.py -q --no-cov` -> 16 passed; `python -m pytest tests/v1/ tests/run/ -q --no-cov` -> 22 passed; focused `ruff`, focused `mypy`, and `git diff --check` passed.
- PR state: PR **#519** open/non-draft, closes #518, labels [agent:codex, agents:keepalive, autofix]. `codex`/`codex-automation` labels are not present in this repo label list; `agent:retry` exists but was not required for initial creation. Cap-health after PR creation sees #519 as draining with active Gate/Gate Followups/Autofix evidence.
- Next action: keepalive/Gate owns PR #519.

## 2026-06-02T04:12:00Z - opener (codex) PR #500 typecheck recovery

- Selected recovery lane: `stranske/Inv-Man-Intake` PR `#500` (`codex/issue-498-browser-artifact`), source issue `#498`.
- Cap-drain action: removed stale `agent:needs-attention` label after keepalive completion evidence; cap-health then reported PR #500 and PR #501 drainable with no non-drainable cap blocker.
- Concrete failing check inspected: `Gate / Python CI / typecheck-mypy` job `78997679166` failed on redundant casts in `src/inv_man_intake/readiness/throughput.py`.
- Fix pushed: `877b8f8` (`fix(readiness): drop redundant throughput casts`) removes the three redundant package metadata casts while preserving later `cast(Any, ...)` calls.
- Local validation before push:
  - `uv run mypy --config-file pyproject.toml --exclude .workflows-lib src` -> passed (`Success: no issues found in 75 source files`).
  - `uv run ruff check src/inv_man_intake/readiness/throughput.py` -> passed.
- Post-push note: local validation generated an untracked `uv.lock` in the automation worktree; it was not committed.
- Current state: PR #500 is waiting on fresh async Gate/keepalive checks for head `877b8f8`. PR #501 is a separate same-issue duplicate/concurrent opener PR that was green during this round and should be handled by closer/queue drain policy before source issue disposition.

## 2026-06-02T03:52:55Z - opener (codex) issue #498 PR materialized

- Repo: `stranske/Inv-Man-Intake`
- Issue: `#498` (`Add real browser verification artifact for stlite/Pyodide demo evidence`)
- Branch: `codex/issue-498-browser-artifact`
- Worktree: `/Users/teacher/.codex/automations/pd-workloop-resume/worktrees/inv-issue-498-browser-artifact`
- Owner decision recorded on source issues `#469` and `#470`: require real headless-browser/Pyodide evidence before closure.
- Implemented browser evidence gate:
  - Added `scripts/verify_stlite_browser.py`.
  - Repinned `@stlite/mountable` from nonexistent `0.76.0` to published `0.75.0`.
  - Removed `langsmith>=0.4.59` from stlite browser requirements because Pyodide cannot install its non-pure-Python transitive wheels and the demo intentionally uses in-memory tracing.
  - Added Pyodide/sqlite fallback in `app/streamlit_app.py` that still computes `0.7809` via the real scoring engine when browser Pyodide lacks `sqlite3`.
  - Wrote pass artifacts: `app/live-verification-artifacts/browser-demo-score.png` and `app/live-verification-artifacts/browser-demo-score.json`.
- Validation:
  - `uv run pytest --no-cov tests/app/test_streamlit_app_smoke.py tests/app/test_stlite_browser_verification.py` -> 8 passed.
  - `uv run pytest --no-cov tests/test_dependency_version_alignment.py tests/app/test_streamlit_app_smoke.py tests/app/test_stlite_browser_verification.py` -> 9 passed after adding the missing Playwright lock pins.
  - `uv run ruff check scripts/verify_stlite_browser.py app/streamlit_app.py tests/app/test_streamlit_app_smoke.py tests/app/test_stlite_browser_verification.py tests/test_dependency_version_alignment.py` -> passed.
  - `uv run --extra dev python scripts/verify_stlite_browser.py --browser-channel chrome` -> pass; rendered `Final score 0.7809` in headless Chrome.
- PR: `#500` (`https://github.com/stranske/Inv-Man-Intake/pull/500`)
- Head: `2aee65fa3fb582e3ed092ab0a2cfa342481d849d`.
- PR state: open, non-draft, closes only follow-up issue `#498`; source issues `#469` and `#470` remain related-only and open for verifier/closer disposition.
- Labels: `agent:codex`, `agent:retry`, `agents:keepalive`, `autofix`, `autofix:patch`; stale `needs-human` / `agent:needs-attention` labels from earlier pre-fix failures were removed.
- CI state at 2026-06-02T03:56Z: Gate passed; Python 3.12 and Python 3.13 matrix jobs passed; previous Python matrix failure was `requirements.lock is missing pinned versions for: playwright`, fixed in amended head.
- Workspace hygiene: Code-root audit ran after creating this automation worktree and reported only canonical/allowed entries.
- Next action: closer/verifier should review PR `#500` and the committed PNG/JSON browser artifacts before closing source issues `#469`/`#470`.
