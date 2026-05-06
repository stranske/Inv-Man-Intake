# Autofix diagnostics for PR #388 (head 90f1593a)

Date: 2026-05-06
Head SHA: `90f1593a0d5891aad8912d5b54973989752667c7`

## Local reproduction

- `ruff check src tests`: pass
- `mypy src/inv_man_intake`: pass
- `pytest -q`: pass (`427 passed`)
- Coverage threshold met locally (`91.32%`, required `80%`)

## Observed blocker pattern

Failing jobs from run context:

- `Python CI / python 3.12` failed at `Finalize check results`
- `Python CI / python 3.13` failed at `Finalize check results`
- `gate-summary` failed at `Enforce Gate success`

This branch currently differs from `origin/main` in protected workflow files:

- `.github/workflows/agents-verify-to-new-pr.yml`
- `.github/workflows/maint-coverage-guard.yml`

In `agent-standard`, workflow-file remediation is blocked by policy, and this aligns with repeated failures surfacing only at finalization/gate enforcement rather than Python quality checks.

## Maintainer action required

1. Open run `25454438839` and inspect stderr for `Finalize check results` in both Python matrix jobs.
2. If the finalizer is rejecting workflow changes/policy constraints, resolve in `stranske/Workflows` and re-sync this repo (per `AGENTS.md`).
3. If workflow edits in this PR are intentional, re-run with `agent-high-privilege` approval for workflow changes.
