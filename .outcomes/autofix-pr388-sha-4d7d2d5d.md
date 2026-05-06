## Autofix Attempt Summary (PR #388, head `4d7d2d5dac9dced25141f68246bbe09c66aced04`)

No code-side fix was applied in `src/`, `tests/`, `tools/`, `scripts/`, `agents/`, or `templates/`.

### Local verification
- `ruff check src tests scripts tools`: pass
- `pytest -q --maxfail=1`: pass (`427 passed`)

### CI failure shape from run context
- `Python CI / python 3.12`: failed at `Finalize check results`
- `Python CI / python 3.13`: failed at `Finalize check results`
- `gate-summary`: failed at `Enforce Gate success`

### Assessment
The failure does not reproduce as a Python source/test issue in this repository snapshot. The consistent failure point is the workflow finalizer/gate layer.

### Next checks for maintainer
1. Open run `25456487229` and inspect stderr for `Finalize check results` in both Python matrix legs.
2. If finalizer/policy enforcement is the direct cause, resolve in `stranske/Workflows` (source of truth) and sync this consumer repo.
3. Re-run gate for PR #388 after upstream workflow/policy correction.
