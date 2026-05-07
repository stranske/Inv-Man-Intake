<!-- autofix diagnostic breadcrumb for PR #397 -->

# CI Autofix Diagnostic

- Date: 2026-05-07
- Gate run: https://github.com/stranske/Inv-Man-Intake/actions/runs/25477150283
- PR: #397
- Head SHA: `cd6686c62e5cfc588508ba588f124403b8fad6f9`

## Observed failure

- Job: `Python CI / select reusable CI scope`
- Failing step: `Checkout Workflows helper`
- Downstream: `gate-summary` failed at `Enforce Gate success` because gate checks were already failing.

## Triage result

- The failing step is inside reusable workflow infrastructure sourced from `stranske/Workflows`.
- This repository already has synced helper scripts under `.github/scripts/`, so the issue is likely checkout/auth/ref handling in the reusable workflow path.
- In `agent-standard`, workflow files are protected and cannot be edited locally for autofix.
- Local code check: `pytest -q tests/test_workflow_validation.py` ran with `6 passed`; the command exited non-zero only because the repo-wide `--cov-fail-under=80` threshold is expected to fail on a narrow subset run.

## Required human follow-up

- Add `needs-human` on PR #397.
- Inspect the `Checkout Workflows helper` step implementation in `stranske/Workflows` (reusable CI workflow used by `.github/workflows/ci.yml`) for token access/ref resolution on this PR event.
- Re-run Gate after Workflows-side fix or sync.
