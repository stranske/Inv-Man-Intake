# Original source issue #1019

Source: https://github.com/stranske/Inv-Man-Intake/issues/1019

Captured from the actual issue body during the 2026-10-17T19:21Z closer round.
Historical checkbox state is preserved; see README for independently observed acceptance.

## Why

`docs/INV_MAN_INTAKE_PLAN_V1.md` (Enrichment and Scoring Decisions) and `docs/PRODUCT_CONTRACT.md` (IMI-5) promise asset-class-specific priority scores with evidence-backed, explainable components; `docs/contracts/scoring_explainability.md` defines the reconciliation. In production, `src/inv_man_intake/v1_smoke.py:399` sets `score = None` with reason `evidence_backed_score_components_unavailable` and only computes a score when `smoke_mode`, using the hardcoded `_score_components` at `:840-851` (0.80, 0.78, 0.69, 0.74). `src/inv_man_intake/run.py:232` therefore emits `final_score=None` and `scoring:unavailable`, and `tests/cli/test_ingest_entrypoint.py:189` asserts that even for a valid three-row workbook. IMI-5 stays PARTIAL, and analysts get no priority from submitted evidence.

Current source readback: `src/inv_man_intake/v1_smoke.py:399` at `667fe10bbff63ba67eb99954319aa7f55486a312` (file SHA-256 `b30f6bc43214239bd30f77c5d0f49f81b7a4c201f662253cfe7175a68da968a4`). Earlier detailed line ranges and reproductions retain their reviewed-commit provenance; intervening anchor changes were checked for relevance.

## Scope

- Add deterministic evidence-to-component mapping, normalization and minimum-evidence rules for the five existing components, with explicit reviewed analyst input where extraction is insufficient.
- Build a production `ScoreSubmission` using the canonical asset-class registry, pass it through `gate_scoring_submission` and `compute_score`.
- Emit component provenance and reconciled explainability through `src/inv_man_intake/run.py`, keeping named unavailable outcomes for insufficient evidence.

## Non-Goals

- Do not restore hardcoded smoke components or fabricate benchmark data.
- Do not add external enrichment.
- Do not change weight sets or red-flag rules in the scoring engine.
- Do not remove the fixture-backed smoke path or browser demo.
- Scaffold-only or partial completion does not count as done: deliver the specific Scope behavior and Acceptance Criteria evidence, rather than only a helper, an unconnected call path or an empty passing test run.

## Tasks

- [ ] Add `src/inv_man_intake/v1_smoke.py` (new helper next to `_score_components` at `:840`) mapping extracted fields and workbook metrics to each of the five components, with documented minimum-evidence thresholds.
- [ ] Replace the `score = None` production branch at `src/inv_man_intake/v1_smoke.py:399` with construction of `ScoreSubmission`, `gate_scoring_submission` and `compute_score` using `weights_for_registry()`; keep `_score_components` for smoke only.
- [ ] Build `explainability` via `build_explainability_payload` with document/page or analyst provenance per component, and surface it through `src/inv_man_intake/run.py:232`.
- [ ] Keep the `scoring:unavailable` warning in `src/inv_man_intake/run.py:232` and the `evidence_backed_score_components_unavailable` reason in `src/inv_man_intake/v1_smoke.py:399` when evidence is below minimum.
- [ ] Add CLI tests in `tests/cli/test_ingest_entrypoint.py` for two asset classes, within-class input variation with component-specific expected values, and insufficient evidence; replace the null-score assertion near line 189.
- [ ] Add a component-specific deliberate-break test (constants replacing derived components) to `tests/v1/test_smoke_contract_coverage.py` or the CLI tests, and update `docs/PRODUCT_CONTRACT.md` IMI-5 to the proven behavior.

## Acceptance Criteria

- [ ] `pytest tests/cli/test_ingest_entrypoint.py -k score` shows numeric `final_score` for two supported asset classes with resolvable provenance and contributions reconciling per `docs/contracts/scoring_explainability.md`.
- [ ] Changing one relevant submitted input changes the corresponding component value and the aggregate, asserted by component.
- [ ] Insufficient inputs yield `final_score: null`, the named unavailable reason and a `scoring:unavailable` warning.
- [ ] `pytest tests/scoring/test_engine.py tests/test_v1_acceptance_smoke.py tests/baseline/test_invariants.py` still passes.
- [ ] Deliberate-break gate: after adding the scope-specific regression in `tests/cli/test_ingest_entrypoint.py`, temporarily disconnect its corresponding Scope change at `src/inv_man_intake/v1_smoke.py`; that regression must fail on the described behavior. Restore the change and rerun it successfully, capturing both outcomes.

## Implementation Notes

- `src/inv_man_intake/v1_smoke.py:399` - production null branch and smoke gate.
- `src/inv_man_intake/v1_smoke.py:840` - hardcoded smoke components.
- `src/inv_man_intake/v1_smoke.py:852` - `_explainability_inputs`.
- `src/inv_man_intake/run.py:232` - `final_score`, warnings.
- `docs/PRODUCT_CONTRACT.md` (IMI-5, known gaps), `docs/contracts/scoring_explainability.md`, `docs/INV_MAN_INTAKE_PLAN_V1.md`.
- `tests/cli/test_ingest_entrypoint.py`, `tests/scoring/test_engine.py`, `tests/test_v1_acceptance_smoke.py`, `tests/v1/test_smoke_contract_coverage.py`, `tests/baseline/test_invariants.py`.
- Execution authority: the owner released the intake hold on 2026-10-16 (recorded decision, Claude Code campaign session). Auto-pilot, keepalive and runner assignment are permitted for this issue under the normal priority order.

<!-- repo-review-finding: stranske/Inv-Man-Intake#4628911e5f25 -->

<!-- repo-review-item: stranske/Inv-Man-Intake#4628911e5f25 -->


