# Inv-Man-Intake app behavior baseline kit

Scenario-driven wiring / sensibility / regression tests built on the shared
**`baseline_kit`** package. Only the app-specific pieces live here.

## Requires

`baseline_kit` (the shared core) must be importable. It lives in
`stranske/Workflows` under `packages/app-baseline-kit`:

```bash
pip install "app-baseline-kit @ git+https://github.com/stranske/Workflows.git#subdirectory=packages/app-baseline-kit"
```

It is declared in this repo's `pyproject.toml` `[project.optional-dependencies]
dev`, so `pip install -e ".[dev]"` pulls it (plus `pytest-regressions`).

## Target surface

The **deterministic compute** `inv_man_intake.scoring.engine.compute_score` —
reduces a manager `ScoreSubmission` (an asset class plus the five normalized
`[0, 1]` component scores) to a weighted total `ScoreResult` with a per-component
contribution breakdown and optional red-flag cap/block overrides, with no DB /
network / LLM. The weight schema is in `src/inv_man_intake/scoring/weights.py`
and `config/scoring_weights/`.

## Layout

```
adapter.py                # base submission + patch -> flat metrics dict (the only app glue)
catalog.yaml              # base submission + scenario patches + directional checks
invariants.py             # economic bounds -> baseline_kit.InvariantResult
test_golden.py            # golden master of each scenario's flattened metrics
test_directional.py       # metamorphic checks (better sleeves -> higher score; cap/block -> lower)
test_invariants.py        # invariants on base + every scenario
test_coverage_manifest.py # metric-key coverage -> docs/reports/baseline-coverage.md
```

## Scenario model

A *scenario* is the base submission (`catalog.yaml` `base`) with an optional
ordered `patch` applied. The patch DSL (`adapter.apply_patch`) supports
`set_component`, `scale_component`, `shift_all`, `set_asset_class`,
`red_flag_cap`, `red_flag_block` — enough to make each variant directionally
predictable (raise every sleeve → higher score; cap/block → lower final score).

The flat metrics dict each run produces:

- `base_score`, `final_score`
- `contribution.<component>` for each of the five components
- `red_flag_applied` (0/1)

## Running

```bash
pytest tests/baseline/                                   # full suite
pytest tests/baseline/test_golden.py --force-regen       # re-bless after an intended change
BASELINE_REFRESH_REPORT=1 pytest tests/baseline/test_coverage_manifest.py  # refresh report
```

## Invariants enforced

For the base submission and every scenario, grounded in
`src/inv_man_intake/scoring/engine.py`:

- `0 <= base_score <= 1`, `0 <= final_score <= 1` (convex combination of `[0, 1]`
  components with weights summing to `1.0`)
- every emitted scalar is finite (no NaN/inf)
- all required keys present (`base_score`, `final_score`, the five
  `contribution.*`, `red_flag_applied`)
- `sum(contribution.*) == base_score` (the engine sums the per-component
  contributions)
- `0 <= contribution.<c> <= weight(<c>)` for each component
- `final_score <= base_score` (no red-flag override can raise the score)
- `red_flag_applied == 1` when a block applies, or when a cap lowers
  `final_score` below `base_score`
