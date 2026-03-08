# Scoring weight configuration runbook

This runbook describes the v1 asset-class scoring weight files and safe tuning steps.

## Files and schema

- Directory: `config/scoring_weights/`
- One TOML file per launch asset class.
- Required top-level keys:
  - `asset_class` (string)
  - `version` (string, `v1` default)
  - `[weights]` table
- Required weight keys:
  - `performance_consistency`
  - `risk_adjusted_returns`
  - `operational_quality`
  - `transparency`
  - `team_experience`

Validation rules:
- Each weight must be numeric between `0` and `1`.
- Required keys must be complete (no missing/extra component names).
- Weights must sum to `1.0`.
- All launch classes must have files: `equity`, `credit`, `macro`, `multi_strategy`, `real_assets`.

## Default rationale (v1)

- `equity`: performance and risk-adjusted returns weighted highest.
- `credit`: balanced return/risk with stronger operational quality emphasis.
- `macro`: stronger emphasis on risk-adjusted outcomes and transparency.
- `multi_strategy`: balanced spread to avoid overweighting one signal.
- `real_assets`: higher operational quality to account for reporting/valuation complexity.

## Tuning procedure

1. Update one asset class file at a time.
2. Keep all component names present and ensure total equals `1.0`.
3. Run `pytest -q tests/scoring/test_weights_config.py --no-cov`.
4. If adjusting strategy behavior, pair with regression updates in scoring engine tests.
5. Record rationale and date in PR summary for reproducibility.
