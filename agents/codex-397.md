<!-- autofix diagnostic breadcrumb for PR #397 -->

# CI Autofix Diagnostic

- Date: 2026-05-07
- Gate run: https://github.com/stranske/Inv-Man-Intake/actions/runs/25477048050
- PR: #397
- Head SHA: `75acc049efba462cebda1cbea3a1c63e29447036`

## Observed failure

- Job: `Python CI / select reusable CI scope`
- Failing step: `Checkout Workflows helper`
- Downstream: `gate-summary` failed at `Enforce Gate success` because gate checks were already failing.

## Triage result

- The failing step is inside reusable workflow infrastructure sourced from `stranske/Workflows`.
- In `agent-standard`, workflow files are protected and cannot be edited locally for autofix.
- Local repo checks did not expose an application-code failure tied to this checkout step.

## Required human follow-up

- Add `needs-human` on PR #397.
- Inspect the reusable workflow checkout logic and credentials/ref handling in `stranske/Workflows` for the `Checkout Workflows helper` step.
- Re-run Gate after Workflows-side fix or sync.
