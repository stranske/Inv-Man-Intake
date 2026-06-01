"""Inv-Man-Intake app behavior baseline kit.

Built on the shared ``baseline_kit`` package -- this directory contains only the
app-specific pieces (adapter, catalog, invariant bounds). The generic harness
(directional engine, invariant assertion, golden glue, coverage manifest) is
imported from ``baseline_kit``, the same core the TMP / PAEM / trip-planner /
Counter_Risk kits use.

Target surface: ``inv_man_intake.scoring.engine.compute_score`` -- a
deterministic compute (no DB, no network, no LLM) that reduces a manager
``ScoreSubmission`` (asset class + five normalized component scores) to a
weighted total ``ScoreResult`` with a per-component contribution breakdown and
optional red-flag cap/block overrides.
"""
