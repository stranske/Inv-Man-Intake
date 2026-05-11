# Workloop State

## 2026-05-11T02:34:30Z - opener lane issue #26 PR materialization

- Automation: `pd-workloop-resume` (codex opener lane).
- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#26` (`Image feedback capture contract and service`, `priority:normal`).
- Source PR: `#413` (`https://github.com/stranske/Inv-Man-Intake/pull/413`), non-draft, labels `agent:codex` + `agents:keepalive` + `autofix`.
- Branch: `codex/issue-26-image-feedback`.
- Selection:
  - ACTION A succeeded from the neutral Code workspace; sentinel `active.*` pointed at closer/verifier state and was treated as cross-lane informational state only.
  - Required discovery ran across `repo-review-approved`, `priority:high`, `priority:normal`, and `priority:low`.
  - High-priority `trip-planner#1130` and `trip-planner#1129` were skipped because both are reopened for verifier sequencing after existing merged PRs.
  - Cap-health after infra repair reported `total_opener_owned=2`, `raw_cap_reached=false`, `normal_cap_reached=false`, and `non_drainable_cap_blocker=false`; helper execution required Python 3.12 in `PATH` because the default Python 3.9 cannot import `datetime.UTC`.
- Implementation:
  - Added `ImageFeedbackRecord` with required-field, ISO timestamp, and 1-5 quality-rank validation.
  - Added visual-artifact feedback persistence keyed by `(artifact_id, reviewer)` so repeated reviews update the previous row.
  - Added `VisualArtifactFeedbackService` for create/read/list feedback operations and re-exported it from `inv_man_intake.images`.
  - Documented feedback governance and the rank scale in `docs/runbooks/visual_artifact_extraction.md`.
- Validation passed:
  - `python -m pytest tests/images/test_feedback_service.py tests/data/test_visual_artifact_repository.py tests/images/test_service.py --no-cov` (`12 passed`).
  - `python -m ruff check src/inv_man_intake/contracts/image_feedback_contract.py src/inv_man_intake/images/feedback_service.py src/inv_man_intake/data/provenance.py src/inv_man_intake/data/repository.py src/inv_man_intake/images/__init__.py tests/images/test_feedback_service.py`.
  - `python -m black --check --line-length 100 src/inv_man_intake/contracts/image_feedback_contract.py src/inv_man_intake/images/feedback_service.py src/inv_man_intake/data/provenance.py src/inv_man_intake/data/repository.py src/inv_man_intake/images/__init__.py tests/images/test_feedback_service.py`.
  - `python -m mypy src/inv_man_intake/contracts/image_feedback_contract.py src/inv_man_intake/images/feedback_service.py src/inv_man_intake/data/provenance.py src/inv_man_intake/data/repository.py`.
  - `git diff --check`.
- Relay event emitted: `pr_opened active.source_repo=stranske/Inv-Man-Intake active.source_issue=26 active.source_pr=413 active.next_action=wait_for_keepalive`.
- Post-open state:
  - PR `#413` is open and non-draft with required routing labels.
  - Initial checks are mostly pending; one synthetic `Gate / gate` row reported `fail` because path classification was cancelled while newer Gate/CI jobs were still queued/pending.
- Next action: keepalive's Codex runner takes over for CI fixups or review-comment work; opener is done with this lane.

## 2026-05-11T01:05:15Z - opener lane issue #25 PR materialization

- Automation: `pd-workloop-resume` (codex opener lane).
- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#25` (`Baseline informative-vs-boilerplate image classifier`, `priority:normal`).
- Branch: `codex/issue-25-image-classifier`.
- Selection:
  - ACTION A succeeded from the neutral Code workspace; sentinel `active.*` pointed at closer/verifier state and was treated as informational.
  - Required priority discovery ran across supported repos. High-priority issues were skipped because they were already represented by existing PR/verifier lanes or explicit operational skips.
  - Cap-health before selection reported `total_opener_owned=4`, `raw_cap_reached=false`, `normal_cap_reached=false`, and `non_drainable_cap_blocker=false`.
  - Infra repair removed stale `agent:needs-attention` from PR `#411`; post-repair cap-health reported `#411` draining and raw cap still below 5.
- Implementation:
  - Added `inv_man_intake.images.classifier.classify_visual_artifact`, returning deterministic `label`, `confidence`, `reason_codes`, and `rationale`.
  - Added heuristic signals for chart/performance terms, numeric chart markers, text density, logo/disclaimer boilerplate terms, source-ref markers, and low-density fallback handling.
  - Re-exported the classifier API from `inv_man_intake.images`.
  - Added `docs/contracts/image_classification.md` with the classifier contract, limitations, and human override path.
  - Updated `docs/runbooks/visual_artifact_extraction.md` to link extraction output to the classification contract.
- Validation passed:
  - `UV_CACHE_DIR=/private/tmp/uv-cache-inv-25 uv run pytest tests/images/test_classifier.py tests/images/test_extractor.py --no-cov` (`8 passed`).
  - `UV_CACHE_DIR=/private/tmp/uv-cache-inv-25 uv run ruff check src/inv_man_intake/images tests/images/test_classifier.py tests/images/test_extractor.py`.
  - `UV_CACHE_DIR=/private/tmp/uv-cache-inv-25 uv run mypy src/inv_man_intake/images`.
  - `git diff --check`.
- Post-open recovery:
  - PR `#412` opened non-draft with `agent:codex`, `agents:keepalive`, and `autofix`; opener emitted `pr_opened`.
  - Cap-health reported raw cap reached and `#412` as `needs-dispatch-evidence`; infra repair added `agent:retry` and dispatched Gate Followups.
  - Direct checks then showed a branch-local `Python CI / lint-format` failure. Reproduced locally with `uv run black --check src/inv_man_intake/images tests/images/test_classifier.py`, formatted `tests/images/test_classifier.py`, and reran style/type/tests successfully.
- Next action: push the formatting recovery commit; keepalive takes over for remaining asynchronous checks.

## 2026-05-10T04:20:00Z - opener lane issue #313 PR materialization

- Automation: `pd-workloop-resume` (codex opener lane).
- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#313` (`Add same-business-day throughput readiness check`, `priority:low`, `repo-review-approved`).
- Source PR: `#406` (`https://github.com/stranske/Inv-Man-Intake/pull/406`), non-draft, labels `agent:codex` + `agents:keepalive` + `autofix`; `agent:retry` added by infra repair after initial dispatch evidence was missing.
- Branch: `codex/issue-313-throughput-readiness`.
- Selection:
  - ACTION A succeeded from the neutral Code workspace and full fleet discovery ran across supported repos using `priority:high`, `priority:normal`, and `priority:low`.
  - Cap-health after infra repair reported `total_opener_owned=3`, `raw_cap_reached=false`, `normal_cap_reached=false`, and `non_drainable_cap_blocker=false`.
  - Skipped `Workflows#2073` as an operational auth-expiry alert, `Inv-Man-Intake#381/#382`, `Manager-Database#910`, `Trend_Model_Project#5168/#5169/#5170/#5172`, `Counter_Risk#476`, and `Pension-Data#320/#321` because they are already linked to existing PRs or verifier/closer disposition.
  - Selected `Inv-Man-Intake#313` as the oldest remaining eligible low-priority implementation issue with no linked PR.
- Implementation:
  - Added `inv_man_intake.readiness.throughput`, a local deterministic CLI that runs the offline v1 fixture batch and writes `reports/readiness/throughput_readiness.json`.
  - Added threshold-handling and queue/audit timing spans to the v1 smoke pipeline while preserving the existing scoring parent-span contract.
  - Added readiness tests for successful report generation, failure on missing stage/scoring evidence, and CLI exit behavior.
  - Documented the command in the v1 plan, README, and `docs/runbooks/throughput_readiness.md`; ignored the generated readiness report path.
- Validation passed:
  - `UV_CACHE_DIR=/private/tmp/uv-cache-inv-313 uv run --extra dev python -m inv_man_intake.readiness.throughput --output reports/readiness/throughput_readiness.json`.
  - `UV_CACHE_DIR=/private/tmp/uv-cache-inv-313 uv run --extra dev python -m pytest tests/readiness/test_throughput_readiness.py tests/test_v1_acceptance_smoke.py --no-cov` (9 passed).
  - `UV_CACHE_DIR=/private/tmp/uv-cache-inv-313 uv run --extra dev ruff check src/inv_man_intake/readiness src/inv_man_intake/v1_smoke.py tests/readiness/test_throughput_readiness.py`.
  - `UV_CACHE_DIR=/private/tmp/uv-cache-inv-313 uv run --extra dev black --check src/inv_man_intake/readiness src/inv_man_intake/v1_smoke.py tests/readiness/test_throughput_readiness.py`.
  - `UV_CACHE_DIR=/private/tmp/uv-cache-inv-313 uv run --extra dev mypy src/inv_man_intake/readiness src/inv_man_intake/v1_smoke.py`.
- Relay event emitted: `pr_opened active.source_repo=stranske/Inv-Man-Intake active.source_issue=313 active.source_pr=406 active.next_action=wait_for_keepalive`.
- Post-open cap-health: infra repair added `agent:retry` and dispatched Gate Followups; fresh cap-health at `2026-05-10T04:11:10Z` reported `#406` as `draining` with an active Gate run, `total_opener_owned=4`, `raw_cap_reached=false`, `normal_cap_reached=false`, and `non_drainable_cap_blocker=false`.
- Next action: keepalive's Codex runner takes over for CI fixups or review-comment work; opener is done with this lane.

## 2026-05-09T15:43:30Z - opener lane PR #404 export toggle remediation

- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#401`.
- Source PR: `#404`, branch `codex/issue-401-langsmith-trace-export`.
- Blockers addressed:
  - Review thread on `Tracer.from_env(...)`: `LANGCHAIN_TRACING_V2=true` plus an API key no longer selects `LangSmithTraceSink` by itself; LangSmith export now also requires `INV_MAN_TRACING_ENABLED=true` or `LANGSMITH_TRACING_ENABLED=true`.
  - CI lint-format remained covered by the exact Black command.
- Validation passed:
  - `uv run black --check --line-length 100 --exclude '(\.venv|\.workflows-lib|node_modules)' .`.
  - `uv run pytest tests/observability/test_langsmith_export.py tests/observability/test_setup_validation.py tests/observability/test_tracing_toggle.py --no-cov` (33 passed).
  - `uv run ruff check src/inv_man_intake/observability/tracing.py src/inv_man_intake/observability/setup_validation.py tests/observability/test_langsmith_export.py`.
- Next action: push this branch update, then re-check PR `#404` for fresh CI and review-thread state.

## 2026-05-09T15:27:18Z - closer lane PR #404 lint-format remediation

- Automation: `imi-merge-verify-closer` (codex closer lane).
- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#401` (`Wire real LangSmith trace export so the documented runbook actually emits spans`, `priority:normal`, `repo-review-approved`).
- Source PR: `#404` (`https://github.com/stranske/Inv-Man-Intake/pull/404`), branch `codex/issue-401-langsmith-trace-export`.
- Batch-safe sweep before selection:
  - Closed `stranske/Trend_Model_Project#5238` after merged PR `#5263` had a durable Provider Comparison Report with OpenAI PASS and Anthropic PASS, and GraphQL review-thread audit showed 0 unresolved threads.
  - Recorded `issue_closed`, recorded the batch sweep, then ran one deferred `reset-chain`.
- Selection:
  - Full fleet discovery ran across supported repos despite the single-slot sentinel active lane.
  - PR `#404` was selected as the one complex lane because it was open, non-draft, issue-linked to `#401`, in-scope agent work, and CI had a concrete `Python CI / lint-format` failure.
- Blocker found:
  - CI job `Python CI / lint-format` on run `25604595641`, job `75164218682`, failed only because Black would reformat `src/inv_man_intake/observability/setup_validation.py`.
- Action taken:
  - Fast-forwarded the local PR worktree to `origin/codex/issue-401-langsmith-trace-export` at `75f4fd1`.
  - Ran Black on `src/inv_man_intake/observability/setup_validation.py`; the only source change is the expected blank line before `SetupValidationResult`.
- Validation passed:
  - `python -m black --check --line-length 100 --exclude '(\.venv|\.workflows-lib|node_modules)' .` (184 files left unchanged).
  - `python -m pytest tests/observability/ tests/test_v1_acceptance_smoke.py --no-cov` (45 passed).
  - `python -m ruff check src/inv_man_intake/observability/setup_validation.py tests/observability/test_langsmith_export.py`.
- Post-action state:
  - Pushed formatting remediation commit `402cf0e` to PR `#404`.
  - Posted PR comment `https://github.com/stranske/Inv-Man-Intake/pull/404#issuecomment-4412869367` with the validation evidence.
  - Immediate post-push check read showed fresh checks queued/pending, including `Observability Smoke`, `Python CI / Validate inputs`, `Resolve review target`, `classify changed paths`, and `guard`.
  - No terminal merge/verify event fired for PR `#404` in this round.
- Next action: after push, re-check PR `#404`; if fresh checks are green and no unresolved review threads appear, merge it and apply `verify:compare`.

## 2026-05-09T15:07:41Z - opener lane issue #401 PR materialization

- Automation: `pd-workloop-resume` (codex opener lane).
- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#401` (`Wire real LangSmith trace export so the documented runbook actually emits spans`, `priority:normal`, `repo-review-approved`).
- Source PR: `#404` (`https://github.com/stranske/Inv-Man-Intake/pull/404`), non-draft, labels `agent:codex` + `agents:keepalive` + `autofix`.
- Branch: `codex/issue-401-langsmith-trace-export`.
- Selection:
  - ACTION A succeeded from the neutral Code workspace and full fleet discovery ran across supported repos.
  - Cap-health after infra repair reported `total_opener_owned=4`, `raw_cap_reached=false`, `normal_cap_reached=false`, and `non_drainable_cap_blocker=false`.
  - Skipped `Workflows#2073` as an operational auth-expiry alert and `Inv-Man-Intake#381` because it was already served by merged PR `#400` and is now a verifier/closer lane.
  - Selected `Inv-Man-Intake#401` as the next actionable issue; no existing open PR was found for this issue/title.
- Implementation:
  - Added `LangSmithTraceSink`, wired `Tracer.from_env(...)` to select it when tracing is enabled and `LANGSMITH_API_KEY` is present, and kept `InMemoryTraceSink` as the offline fallback with a warning.
  - Added runtime `langsmith` dependency and re-exported LangSmith sink/constants from `inv_man_intake.observability`.
  - Extended setup validation with `--probe` / `probe_emit=True` using an injectable mocked client for tests and a real `langsmith.Client` at runtime.
  - Updated the LangSmith runbook and README to document real export plus the probe command.
- Validation passed:
  - `python -m pytest tests/observability/ tests/test_v1_acceptance_smoke.py --no-cov` (44 passed).
  - `python -m ruff check src/inv_man_intake/observability tests/observability docs/runbooks/langsmith_tracing.md README.md pyproject.toml`.
  - `python -m mypy src/inv_man_intake/observability`.
  - `PYTHONPATH=src python -c 'import langsmith; import inv_man_intake.observability.langsmith_sink'`.
  - `git diff --check`.
- Relay event emitted: `pr_opened active.source_repo=stranske/Inv-Man-Intake active.source_issue=401 active.source_pr=404 active.next_action=wait_for_keepalive`.
- Next action: keepalive's Codex runner takes over for CI fixups or review-comment work; opener is done with this lane.

## 2026-05-09T09:28:09Z - closer lane PR #403 review-thread remediation

- Automation: `imi-merge-verify-closer` (codex closer lane).
- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#382` (`Audit and remediate v1-readiness fixture-vs-real-design drift across intake persistence, extraction, and queue contracts`, `priority:normal`, `repo-review-approved`, `repo-review-meta-audit`).
- Source PR: `#403` (`https://github.com/stranske/Inv-Man-Intake/pull/403`), branch `codex/issue-382-v1-smoke-contract-audit`.
- Selection:
  - ACTION A succeeded from the neutral Code workspace and full fleet discovery ran across supported repos.
  - Batch-safe sweep closed `stranske/Counter_Risk#552`, merged `stranske/Counter_Risk#573`, applied `verify:compare`, and reopened issue `#477` for verifier sequencing.
  - This PR was selected as the one complex lane because it was the sentinel active lane, remained open/non-draft, had green checks and `CLEAN` merge state, but had three unresolved Copilot review threads.
- Blockers found:
  - `tests/v1/test_smoke_contract_coverage.py` treated `core_repository` / `document_store` as missing when passed positionally to `register_intake_bundle[_file]()`.
  - The guard needed to continue catching `from inv_man_intake.queue import state_machine`, which the branch already covered before this closer patch.
  - `workloop-state.md` recorded a machine-specific absolute worktree path in durable repo state.
- Action taken:
  - Added regression coverage for positional and mixed positional/keyword persistence arguments.
  - Reworked the guard to count the third and fourth positional arguments as `core_repository` and `document_store` for both intake registration helpers.
  - Generalized the durable worktree note to avoid a machine-specific absolute path.
- Validation passed:
  - `python -m pytest tests/v1/test_smoke_contract_coverage.py tests/test_v1_acceptance_smoke.py --no-cov` (14 passed).
  - `python -m ruff check tests/v1/test_smoke_contract_coverage.py workloop-state.md`.
  - `python -m black --target-version py312 --check tests/v1/test_smoke_contract_coverage.py`.
  - `git diff --check`.
- Post-action state:
  - Pushed remediation commit `6058466` and resolved all three Copilot review threads.
  - Posted PR comment `https://github.com/stranske/Inv-Man-Intake/pull/403#issuecomment-4412162631` with validation evidence.
  - Fresh post-push checks are pending and GitHub still reports the PR as `BLOCKED` until those checks settle.
- Next action: re-check PR `#403`; if fresh checks are green and no new review threads appear, merge it and apply `verify:compare`.

## 2026-05-09T09:13:00Z - opener lane issue #382 PR materialization

- Automation: `pd-workloop-resume` (codex opener lane).
- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#382` (`Audit and remediate v1-readiness fixture-vs-real-design drift across intake persistence, extraction, and queue contracts`, `priority:normal`, `repo-review-approved`, `repo-review-meta-audit`).
- Source PR: `#403` (`https://github.com/stranske/Inv-Man-Intake/pull/403`), non-draft, labels `agent:codex` + `agents:keepalive` + `autofix`.
- Branch/worktree: `codex/issue-382-v1-smoke-contract-audit` in the selected repo worktree.
- Selection:
  - ACTION A succeeded from the neutral Code workspace.
  - Live priority discovery ran for `priority:high`, `priority:normal`, and `priority:low` across supported repos.
  - Cap-health initially found 4 opener-owned PRs with one stale blocking label on `Counter_Risk#573`; opener infra repair removed `agent:needs-attention`, added `agent:retry`, and fresh cap-health reported 4 drainable opener-owned PRs with no non-drainable blockers.
  - Skipped `Workflows#2073` as a credential/auth-expiration alert, `Inv-Man-Intake#381` as already served by merged PR `#400`, and older normal candidates already linked to open or merged verifier-hold PRs (`Counter_Risk#476/#477/#552`, `Trend_Model_Project#5169/#5170/#5172`, `Manager-Database#910`).
  - Selected `Inv-Man-Intake#382` as the next oldest actionable normal-priority issue.
- Implementation:
  - Added `docs/reports/v1_smoke_contract_audit.md`, classifying v1-smoke-relevant contracts and linking the already converged per-instance fixes: #379/#393, #380/#399, and #381/#400.
  - Added `tests/v1/test_smoke_contract_coverage.py`, an AST/source regression guard that rejects fixture-primary extraction providers, dict-only intake registration calls, and imports from the discarded `inv_man_intake.queue.state_machine` module.
  - No new follow-up issues were filed because the observed v1-smoke-relevant non-end-to-end drift is already covered by the existing converged issue/PR set above.
- Validation passed:
  - `python -m pytest tests/v1/test_smoke_contract_coverage.py tests/test_v1_acceptance_smoke.py --no-cov` (9 passed).
  - `python -m ruff check docs/reports/v1_smoke_contract_audit.md tests/v1/test_smoke_contract_coverage.py`.
  - `python -m mypy tests/v1/test_smoke_contract_coverage.py`.
  - `git diff --check`.
- Relay event emitted: `pr_opened active.source_repo=stranske/Inv-Man-Intake active.source_issue=382 active.source_pr=403 active.next_action=wait_for_keepalive`.
- Next action: keepalive's Codex runner takes over for any CI fixups or review-comment work; opener is done with this lane.

## 2026-05-07T07:50:00Z - opener lane PR #400 materialized

- Automation: `pd-workloop-resume` (claude_code opener lane, scheduled run).
- Source repo: `stranske/Inv-Man-Intake`.
- Source issue: `#381` (`Reconcile validation queue contract: docs describe orphan state machine; integrated path uses different states`, `priority:high`, `repo-review-approved`).
- Source PR: `#400` (`https://github.com/stranske/Inv-Man-Intake/pull/400`), non-draft, labels `agent:claude` + `agents:keepalive` + `autofix`.
- Branch: `claude/issue-381-validation-queue-contract`.
- Selection:
  - Cap-health preflight: `total_opener_owned=2`, `raw_cap_reached=false`, `non_drainable_cap_blocker=false`, `drainable_count=1`. Cap had room.
  - Live priority discovery (high/normal/low) found `Inv-Man-Intake#381` as the oldest unblocked `priority:high` issue with no linked open PR. Manager-Database #976/#977/#978/#979 and Travel-Plan-Permission #1046 were younger; Inv-Man-Intake #379 already linked to in-flight PR #393.
- Action taken:
  - Picked `workflow_validation.py`'s state set (`pending_triage` -> `in_validation` -> `awaiting_manager_response` / `ops_review` -> `completed` / `rejected`) as canonical.
  - Rewrote `docs/contracts/queue_states.md` to that state set, with transition matrix, ownership rules, escalation routes, and import surface.
  - Removed the orphan `src/inv_man_intake/queue/state_machine.py` and its tests.
  - Trimmed `src/inv_man_intake/queue/__init__.py` to assignment + SLA primitives, eliminating the `create_queue_item` name collision.
  - Added `tests/queue/test_v1_smoke_state_transition.py` driving `pending_triage -> in_validation -> completed` keyed to the v1 conflict queue item id, with a regression that legacy state names like `resolved` are rejected.
- Validation passed locally:
  - `python -m pytest tests/queue tests/test_workflow_validation.py tests/test_validation_queue_api.py tests/test_v1_acceptance_smoke.py --no-cov` (28 passed).
  - `ruff check` and `mypy` clean on touched modules.
  - `rg "def create_queue_item" src/inv_man_intake` returned exactly one match (`workflow_validation.py:79`).
- Relay event emitted: `pr_opened active.source_repo=stranske/Inv-Man-Intake active.source_issue=381 active.source_pr=400 active.next_action=wait_for_keepalive`.
- Next action: keepalive's per-agent runner (`reusable-claude-run.yml` via `agent:claude`) takes over from here for any CI fixups or review-comment work; opener is done with this lane.

## 2026-05-07T06:25:00Z - closer lane PR #399 review/CI remediation

- Automation: `imi-merge-verify-closer` (codex closer lane).
- Source issue: `#380` (`Implement and prove real document-bytes extraction in the v1 smoke path`).
- Source PR: `#399` (`https://github.com/stranske/Inv-Man-Intake/pull/399`).
- Branch: `codex/issue-380-real-byte-extraction`.
- Selection:
  - ACTION A succeeded from the neutral Code workspace.
  - Full fleet discovery ran across supported repos; maintenance/dependency PRs were excluded.
  - The sentinel active lane `stranske/Inv-Man-Intake#399` was still open and agent-owned, so it was selected before moving to other repos.
- Blockers found:
  - `Python CI / lint-format` failed on the PR.
  - Five unresolved Copilot review threads were present: explicit orchestrator kwargs, non-idiomatic fallback raising, PDF literal octal/line-continuation escapes, XLSX fixture realism, and `workloop-state.md` repo noise.
- Action taken:
  - Replaced dynamic `ExtractionOrchestrator` kwargs with explicit keyword construction and typed helper extractors.
  - Replaced generator-`throw` fallback raising with a named fallback extractor.
  - Added minimal PDF literal octal escape and escaped line-continuation handling.
  - Replaced the placeholder `.xlsx` bytes with a small ZIP-backed XLSX-like fixture and tightened secondary detection to `PK\x03\x04`.
  - Kept `workloop-state.md` in the PR because this automation requires selected-repo durable root state; the PR thread should be resolved with that disposition.
- Validation passed locally:
  - `python -m ruff check src/inv_man_intake/extraction/providers/pdf_primary.py src/inv_man_intake/v1_smoke.py tests/extraction/test_pdf_primary_provider.py tests/extraction/test_document_byte_provider.py tests/test_v1_acceptance_smoke.py`
  - `python -m black --check src/inv_man_intake/extraction/providers/pdf_primary.py src/inv_man_intake/v1_smoke.py tests/extraction/test_pdf_primary_provider.py tests/extraction/test_document_byte_provider.py tests/test_v1_acceptance_smoke.py`
  - `python -m mypy src/inv_man_intake/extraction/providers/pdf_primary.py src/inv_man_intake/v1_smoke.py`
  - `python -m pytest tests/extraction/test_pdf_primary_provider.py tests/extraction/test_document_byte_provider.py tests/test_v1_acceptance_smoke.py --no-cov`
- Next action:
  - Push the remediation commit, resolve the four code/fixture Copilot threads and disposition the `workloop-state.md` thread, then re-check CI. If checks pass and no new review debt appears, merge `#399` and apply `verify:compare` in a future closer round.

## 2026-05-07T06:05:28Z - opener lane PR materialization

- Automation: `pd-workloop-resume` (codex opener lane).
- Source issue: `#380` (`Implement and prove real document-bytes extraction in the v1 smoke path`).
- Branch: `codex/issue-380-real-byte-extraction`.
- Selection:
  - ACTION A succeeded from the neutral Code workspace.
  - Live priority discovery found high-priority supported issues; `#379` is already linked to open PR `#393`.
  - Cap-health preflight reported `total_opener_owned=4`, `raw_cap_reached=false`, `normal_cap_reached=false`, `non_drainable_cap_blocker=false`; opener has one available slot.
  - `#380` is the oldest high-priority supported issue not already linked to an open opener PR.
- Implementation:
  - Added `PdfPrimaryExtractionProvider`, a dependency-free, text-bearing PDF byte provider that validates PDF framing, extracts literal stream text, emits stable canonical fields with source pages, and calls `validate_extracted_document_result`.
  - Routed v1 smoke primary extraction through `ExtractionOrchestrator` with committed PDF bytes instead of hard-coded smoke fields.
  - Routed the secondary XLSX role through the same orchestrator boundary with deterministic `ops_review` unsupported-format escalation.
  - Added real-byte PDF/no-match/unsupported fixtures, focused provider/orchestrator tests, and docs for current real-byte support.
- Validation passed:
  - `python -m ruff check src/inv_man_intake/extraction/providers/pdf_primary.py src/inv_man_intake/extraction/providers/__init__.py src/inv_man_intake/v1_smoke.py tests/extraction/test_pdf_primary_provider.py tests/extraction/test_document_byte_provider.py tests/test_v1_acceptance_smoke.py`
  - `python -m mypy src/inv_man_intake/extraction/providers/pdf_primary.py src/inv_man_intake/v1_smoke.py`
  - `python -m pytest tests/extraction/test_pdf_primary_provider.py tests/extraction/test_document_byte_provider.py --no-cov`
  - `python -m pytest tests/extraction tests/test_v1_acceptance_smoke.py --no-cov`
  - `rg "fixture-primary|primary_extractor" src/inv_man_intake/v1_smoke.py tests/test_v1_acceptance_smoke.py` returned no matches.
- Commit: `f55eb63` (`Issue #380: prove real-byte extraction smoke path`).
- PR: `#399` (`https://github.com/stranske/Inv-Man-Intake/pull/399`), ready for review, branch `codex/issue-380-real-byte-extraction`, labels `agent:codex`, `agents:keepalive`, `autofix`.
- Relay event emitted: `pr_opened active.source_pr=399 active.next_action=wait_for_keepalive`.

## 2026-03-08 04:10:27 CDT
- Automation: pd-workloop-resume
- Context carry-forward:
  - Issue #39 branch pushed and PR opened at https://github.com/stranske/Inv-Man-Intake/pull/80.
  - Open-PR sweep remained intermittently blocked by `error connecting to api.github.com`.
- Current branch: `codex/issue-37-scoring-engine-red-flag-hooks`.
- Issue in progress: #37 (Scoring engine core and red-flag override hooks).
- Implemented:
  - `src/inv_man_intake/scoring/contracts.py`
  - `src/inv_man_intake/scoring/engine.py`
  - `src/inv_man_intake/scoring/__init__.py`
  - `tests/scoring/test_engine.py`
- Local validation:
  - `ruff check src/inv_man_intake/scoring tests/scoring/test_engine.py` PASS
  - `pytest --no-cov tests/scoring/test_engine.py` PASS (4 tests)

## 2026-03-08 04:10:46 CDT
- Pre-push sync (git-remote-sync): PASS (`git fetch origin --prune`, `git rebase origin/main`).
- Prepared push for issue #37 branch with commit `ae527bd`.

## 2026-03-08 04:13:04 CDT
- PR #81 remediation: fixed `Python CI / lint-format` by applying `ruff format` to scoring engine.
- Pre-push sync (git-remote-sync): PASS (`git fetch origin --prune`, `git rebase origin/main`).
- Prepared push for commit `77aaf93`.

## 2026-03-12 19:25:05 CDT - workloop resume run
- Skills used: issue-completion-audit, issue-pr-workloop, git-remote-sync, workflow-steward, post-push-review.
- Preflight:
  - git ls-remote origin: PASS
  - gh api rate_limit: PASS
- Required initial audit command:
  - Ran 3 attempts with 30s backoff.
  - Failed each attempt at: gh issue list --repo stranske/Inv-Man-Intake --state closed --limit 200 --json number,title,url
- Queue source:
  - docs/reports/issue_completion_queue.tsv was not generated (docs/reports missing).
  - Fallback direct sweep used with priority focus on open audit follow-up issues #145 (C2), #136 (C2), #117 (C3).
- Remote blocker while executing queue actions:
  - Repeated error: "error connecting to api.github.com\ncheck your internet connection or https://githubstatus.com"
  - Attempted per-command retries (5x) for issue mutation commands; still failed.
- Local-only fallback work completed (issue #136 follow-up scope):
  - Implemented timestamp normalization/validation and UTC coercion in queue audit events.
  - Made audit event metadata immutable via MappingProxyType.
  - Switched repository timestamp ordering checks to datetime-based comparisons.
  - Broadened append_queue_action metadata typing to Mapping[str, str].
  - Updated queue audit retention runbook wording to match enforcement behavior.
  - Added tests for metadata immutability, invalid timestamp rejection, Z/offset normalization, and timezone-ordering determinism.
  - Validation: pytest -q --no-cov tests/audit/test_queue_audit.py (9 passed).
- Push/review status:
  - No push performed due to intermittent GitHub API connectivity failures.
- Final audit rerun (2026-03-12 19:30:52 CDT): FAILED after 3 attempts with 30s backoff on the same closed-issues query command.
- Refreshed queue snapshot could not be recorded due recurring GitHub CLI/API failure on closed issue enumeration.
- Push update (2026-03-12 19:32:06 CDT): pushed branch codex/issue-136-thread-disposition-local at commit 66aad4d.
- Post-push PR action: attempted gh pr create (5 retries), all failed with "error connecting to api.github.com".
- Post-push-review follow-up blocked pending API recovery because no PR number could be created/retrieved.
- PR creation recovered: opened PR #172 for issue #136 (branch codex/issue-136-thread-disposition-local).
- CI follow-up: initial lint-ruff failure fixed in commit 6a09b05 and pushed; current checks are pending with no inline review comments yet.
- Queue mutation blocker (2026-03-12 19:34:40 CDT): repeated issue comment/close attempts for #145, #117, and #136 failed despite retries with "error connecting to api.github.com".
- Measurable-progress target status: code/PR progress achieved for priority item #136, but issue closure action for priority-1 items remains blocked by API write failures.

## 2026-03-12 22:21:40 CDT - workloop resume run checkpoint
- Skills active: issue-completion-audit, issue-pr-workloop, git-remote-sync, workflow-steward, post-push-review.
- Preflight:
  - `git ls-remote origin`: PASS
  - `gh api rate_limit`: PASS
- Required initial audit command:
  - Executed 3 attempts with 30s backoff.
  - Failed all attempts at `gh issue list --repo stranske/Inv-Man-Intake --state closed --limit 200 --json number,title,url` inside `run_audit_report.py`.
- Queue work completed this run (3 items processed; includes C3):
  - C2 item: PR #172 / issue #136 follow-up branch updated and pushed (`af5665c`) with inline-feedback fixes + required issue artifacts.
  - C2 item: PR #171 reviewed against inline comments; code path already reflects requested changes, but thread-resolution mutation blocked by API failures.
  - C3 item: issue #117 attempted retrigger (`remove-label needs-human`, `remove-label agents:auto-pilot-pause`, `add-label agents:auto-pilot`) blocked by repeated API failures.
- Push update:
  - 2026-03-12 22:14 CDT pushed `tmp/pr172 -> codex/issue-136-thread-disposition-local` (`ba420cc..af5665c`).
- Current blocker (exact):
  - Repeated `error connecting to api.github.com` during `gh api graphql`, `gh issue edit`, and `gh pr comment` operations.
- Next step in-run:
  - Execute required final audit command until a refreshed queue snapshot is captured.

## 2026-03-12 22:40:30 CDT - final audit + post-push-review
- Post-push-review check for PR #172 executed after >7 minutes from push.
- All post-push-review API calls failed with the same blocker:
  - `error connecting to api.github.com`
- Required final audit command rerun:
  - Executed 10 attempts (`2026-03-13T03:21:29Z` through `2026-03-13T03:38:11Z`).
  - Every attempt failed at: `gh issue list --repo stranske/Inv-Man-Intake --state closed --limit 200 --json number,title,url` from `run_audit_report.py`.
- Queue snapshot status:
  - Refreshed `docs/reports/issue_completion_queue.tsv` could not be regenerated in this run due recurring GitHub API connectivity/error condition above.
- Run disposition:
  - Backlog work advanced on priority item PR #172; remote review-thread/issue mutations remain blocked pending API recovery.

## 2026-03-13 00:09:21 CDT - workloop resume checkpoint
- Queue fallback (audit command failed 3x at closed issue list); processed items target set: #145 (C2), #136 (C2), #117 (C3).
- PR #172 branch synced locally (`workloop-172` from `origin/codex/issue-136-thread-disposition-local`).
- Applied lint-format fix in `src/inv_man_intake/audit/repository.py` to address failing `Python CI / lint-format` signal.
- Validation on branch: `pytest -q --no-cov tests/audit/test_queue_audit.py` (10 passed), `ruff check` passed.

## 2026-03-15 17:19:23 CDT - workloop resume run
- Skills active this run: issue-completion-audit, issue-pr-workloop, git-remote-sync, workflow-steward, post-push-review.
- Preflight:
  - `git ls-remote origin`: PASS
  - `gh api rate_limit`: PASS (read endpoints)
- Required startup audit command:
  - Executed 3 attempts with 30s backoff.
  - All attempts failed at `gh issue list --repo stranske/Inv-Man-Intake --state closed --limit 200 --json number,title,url` inside `run_audit_report.py`.
- Queue processing (3 items, priority-1 first, includes C3):
  - P1/C2 item #145 (PR #69): verified via GraphQL that all tracked review threads are already `isResolved=true`.
  - P1/C2 item #136 (PR #172): verified all 5 review threads are `isResolved=true`; acceptance artifacts (`scripts/list_unresolved_pr_threads.sh`, `docs/pr-76-thread-disposition.md`) present on branch.
  - P1/C3 item #116 (verify follow-up for PR #74): reviewed issue context and queued explicit disposition follow-up action.
- Remote mutation blocker:
  - Repeated write failures on `gh issue comment`/`gh issue close` with exact error:
    - `error connecting to api.github.com`
    - `check your internet connection or https://githubstatus.com`
  - Retried issue #145 close/comment 10 attempts; all failed.
- Queue snapshot recorded (fallback):
  - Wrote `docs/reports/issue_completion_queue.tsv` with current P1/C2/C3 actions and next steps.
- Measurable-progress target:
  - Direct close/mutation of priority-1 item blocked by GitHub write API outages in this run.
  - Verified that one targeted priority-1 unresolved-thread item (#145) is now substantively complete and queued for immediate close once write API recovers.

## 2026-03-15 17:25:31 CDT - final audit rerun result
- Required end-of-run audit command rerun executed with 3 attempts and 30s backoff.
- All attempts failed at the same command inside `run_audit_report.py`:
  - `gh issue list --repo stranske/Inv-Man-Intake --state closed --limit 200 --json number,title,url`
- Fallback refreshed queue snapshot retained at:
  - `docs/reports/issue_completion_queue.tsv`
- Remote write blocker remains active for issue mutation commands during this run.

## 2026-03-15 17:26:37 CDT - push update
- Local commit created: `a8bca72` (`chore(workloop): record p1 queue sweep and final audit blocker`).
- Pre-push sync (git-remote-sync subset):
  - `git fetch origin --prune` PASS
  - `git rebase origin/main` PASS (already up-to-date)
- Pushed branch `codex/issue-136-thread-disposition-resume` to origin.
- Pushed same commit to active PR branch `codex/issue-136-thread-disposition-local` (PR #172 now includes run artifacts).
