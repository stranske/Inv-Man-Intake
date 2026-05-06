# Autofix diagnostics for PR #388 (head 675efd6e)

Date: 2026-05-06
Head SHA: `675efd6efe3b8fa9a665f961f32bd1936de17501`

## Local reproduction

- `ruff check src tests scripts tools`: pass
- `black --check src tests scripts tools`: pass
- `mypy src/inv_man_intake`: pass
- `pytest -q --maxfail=1`: pass (`427 passed`)
- Coverage threshold met locally (`91.32%`, required `80%`)

## CI failure shape from run context

Failing jobs from gate run `25455164732`:

- `Python CI / python 3.12` failed at `Finalize check results`
- `Python CI / python 3.13` failed at `Finalize check results`
- `gate-summary` failed at `Enforce Gate success`

## Assessment

Python quality checks are green locally for this exact head. The failure pattern matches a reusable-workflow finalizer/gate policy failure rather than a failing source/test check.

This PR branch includes workflow-file changes (`.github/workflows/agents-verify-to-new-pr.yml`, `.github/workflows/maint-coverage-guard.yml`). In `agent-standard`, workflow remediation is protected.

## Required human/high-privilege follow-up

1. Open run `25455164732` and inspect stderr in `Finalize check results` for both Python matrix legs.
2. If the finalizer is rejecting protected workflow changes, handle in `stranske/Workflows` and re-sync this consumer repo per `AGENTS.md` ownership.
3. If workflow edits are intentional for this PR, rerun with `agent-high-privilege` approval for workflow changes.
