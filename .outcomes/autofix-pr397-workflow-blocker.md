## Autofix Blocker: PR #397 Gate failure

- Date: 2026-05-07
- Gate run: https://github.com/stranske/Inv-Man-Intake/actions/runs/25476931418
- Head SHA: `54dab545da55b36266e15107fb04d3b6b918667f`

### Observed failure

- Job: `Python CI / select reusable CI scope`
- Failing step: `Checkout Workflows helper`
- Downstream effect: `gate-summary` fails at `Enforce Gate success` because `needs.python-ci.result` resolves to `failure`.

### Why this is blocked here

The failing step is inside reusable workflow logic sourced from `stranske/Workflows` (not consumer repo runtime code under `src/`, `tests/`, `scripts/`, etc.).

In `agent-standard`, workflow-file edits are restricted for this autofix run, and changing the reusable workflow implementation requires an upstream fix in `stranske/Workflows`.

### Required human/upstream action

1. Update the reusable workflow in `stranske/Workflows` that performs `Checkout Workflows helper` to handle missing cross-repo checkout permissions more gracefully (or avoid hard failure for that helper checkout path).
2. Sync the updated workflow behavior back to consumer repos if needed.
3. Re-run Gate for PR #397 after upstream workflow fix.
