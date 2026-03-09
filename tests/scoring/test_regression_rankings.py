"""Regression and calibration tests for scoring stability."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inv_man_intake.scoring.regression import (
    ScoreEntry,
    build_calibration_stats,
    detect_score_drift,
    rank_by_asset_class,
)


def _load_fixture_entries() -> tuple[ScoreEntry, ...]:
    path = Path("tests/fixtures/scoring/launch_asset_class_scores.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return tuple(ScoreEntry(**item) for item in payload)


def test_rankings_are_stable_for_launch_fixture_dataset() -> None:
    entries = _load_fixture_entries()

    ranked = rank_by_asset_class(entries)

    assert ranked["equity"] == ("eq_alpha", "eq_beta", "eq_gamma")
    assert ranked["credit"] == ("cr_alpha", "cr_beta", "cr_gamma")
    assert ranked["macro"] == ("ma_alpha", "ma_beta", "ma_gamma")
    assert ranked["multi_strategy"] == ("ms_alpha", "ms_beta", "ms_gamma")
    assert ranked["real_assets"] == ("ra_alpha", "ra_beta", "ra_gamma")


def test_drift_report_alerts_when_thresholds_are_exceeded() -> None:
    baseline = _load_fixture_entries()
    candidate = tuple(
        ScoreEntry(
            manager_id=entry.manager_id,
            asset_class=entry.asset_class,
            score=(0.69 if entry.manager_id == "eq_alpha" else entry.score),
        )
        for entry in baseline
    )

    report = detect_score_drift(
        baseline,
        candidate,
        max_score_delta=0.05,
        max_rank_movement=1,
    )

    assert report.checked_count == len(baseline)
    assert len(report.alerts) == 1
    alert = report.alerts[0]
    assert alert.manager_id == "eq_alpha"
    assert alert.asset_class == "equity"
    assert alert.score_delta == pytest.approx(0.15)
    assert alert.rank_movement == 2
    assert alert.reasons == ("score_delta", "rank_movement")


def test_drift_report_respects_configurable_thresholds() -> None:
    baseline = _load_fixture_entries()
    candidate = tuple(
        ScoreEntry(
            manager_id=entry.manager_id,
            asset_class=entry.asset_class,
            score=(entry.score - 0.04 if entry.manager_id == "ra_alpha" else entry.score),
        )
        for entry in baseline
    )

    strict = detect_score_drift(baseline, candidate, max_score_delta=0.03, max_rank_movement=1)
    relaxed = detect_score_drift(baseline, candidate, max_score_delta=0.05, max_rank_movement=1)

    assert len(strict.alerts) == 1
    assert strict.alerts[0].manager_id == "ra_alpha"
    assert strict.alerts[0].reasons == ("score_delta",)
    assert relaxed.alerts == ()


def test_calibration_stats_cover_each_asset_class_distribution() -> None:
    entries = _load_fixture_entries()

    stats = build_calibration_stats(entries)

    assert len(stats) == 5
    by_class = {summary.asset_class: summary for summary in stats}

    equity = by_class["equity"]
    assert equity.count == 3
    assert equity.minimum == pytest.approx(0.74)
    assert equity.p50 == pytest.approx(0.79)
    assert equity.p90 == pytest.approx(0.83)
    assert equity.maximum == pytest.approx(0.84)
