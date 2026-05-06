# Autofix diagnostics for PR #388 (head 023c365f)

Date: 2026-05-06
Head SHA: `023c365f08e6df6e19156fe760e4f86cc9cde1a1`

## Local reproduction status

- `ruff check src tests scripts tools`: pass
- `mypy src/inv_man_intake`: pass
- `pytest -q --maxfail=1`: pass (`427 passed`)
- Coverage threshold met locally (`91.32%`, required `80%`)

## CI failure shape from run context

- `Python CI / python 3.12` failed at `Finalize check results`
- `Python CI / python 3.13` failed at `Finalize check results`
- `gate-summary` failed at `Enforce Gate success`

## Assessment

Failure occurs in finalizer/gate orchestration steps, not in repository Python checks reproducible from `src/` and `tests/`.

In `agent-standard`, workflow-file remediation is protected and cannot be performed by this autofix run.

## Required maintainer follow-up

1. Open run `25456031136` and inspect stderr for both `Finalize check results` steps.
2. Confirm whether finalizer/policy enforcement is rejecting workflow-layer conditions.
3. If workflow-level remediation is required, apply at source-of-truth (`stranske/Workflows`) and re-sync this consumer repo.
