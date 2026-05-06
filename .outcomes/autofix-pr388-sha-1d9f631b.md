# Autofix diagnostics for PR #388 (head 1d9f631b)

Date: 2026-05-06
Head SHA: `1d9f631b55e28b087f4dfae412907635989d5e5d`

## Local reproduction

- `ruff check src tests scripts tools`: pass
- `mypy src/inv_man_intake`: pass
- `pytest -q --maxfail=1`: pass (`427 passed`)
- Coverage threshold met locally (`91.32%`, required `80%`)

## CI failure shape

Reported failures from run context:

- `Python CI / python 3.12` failed at `Finalize check results`
- `Python CI / python 3.13` failed at `Finalize check results`
- `gate-summary` failed at `Enforce Gate success`

## Notes

- The PR diff includes protected workflow files under `.github/workflows/`.
- In this `agent-standard` run mode, workflow-file remediation is out of scope.
- Since repository Python checks are green locally, the failure is likely finalizer/policy orchestration rather than source/test behavior.

## Maintainer follow-up

1. Inspect stderr in run `25454899221` for both `Finalize check results` steps.
2. Confirm whether finalizer policy rejected workflow changes.
3. If yes, resolve in `stranske/Workflows` and sync this consumer repo, or re-run with `agent-high-privilege` if workflow changes are intentional.
