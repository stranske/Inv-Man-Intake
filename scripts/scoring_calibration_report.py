#!/usr/bin/env python3
"""Generate a scoring calibration report from fixture or runtime score snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from inv_man_intake.scoring.regression import (
        ScoreEntry,
        build_calibration_stats,
        detect_score_drift,
    )
except ModuleNotFoundError:  # pragma: no cover - script fallback for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from inv_man_intake.scoring.regression import (
        ScoreEntry,
        build_calibration_stats,
        detect_score_drift,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("tests/fixtures/scoring/launch_asset_class_scores.json"),
        help="Path to baseline score snapshot JSON",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=None,
        help="Path to candidate score snapshot JSON (defaults to baseline)",
    )
    parser.add_argument(
        "--max-score-delta",
        type=float,
        default=0.05,
        help="Alert threshold for absolute score drift",
    )
    parser.add_argument(
        "--max-rank-movement",
        type=int,
        default=1,
        help="Alert threshold for ranking movement",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write markdown report to file instead of stdout",
    )
    return parser.parse_args()


def load_entries(path: Path) -> tuple[ScoreEntry, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path}: expected JSON list")
    return tuple(ScoreEntry(**item) for item in payload)


def render_markdown(
    baseline: tuple[ScoreEntry, ...],
    candidate: tuple[ScoreEntry, ...],
    *,
    max_score_delta: float,
    max_rank_movement: int,
) -> str:
    calibration = build_calibration_stats(candidate)
    drift = detect_score_drift(
        baseline,
        candidate,
        max_score_delta=max_score_delta,
        max_rank_movement=max_rank_movement,
    )

    lines: list[str] = []
    lines.append("# Scoring Calibration Report")
    lines.append("")
    lines.append(f"- Baseline entries: {len(baseline)} | Candidate entries: {len(candidate)}")
    lines.append(
        f"- Drift thresholds: score delta <= {max_score_delta:.3f}, "
        f"rank movement <= {max_rank_movement}"
    )
    lines.append("")
    lines.append("## Distribution Summary")
    lines.append("")
    lines.append("| Asset Class | Count | Mean | Std Dev | Min | P50 | P90 | Max |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for summary in calibration:
        lines.append(
            f"| {summary.asset_class} | {summary.count} | {summary.mean:.3f} | "
            f"{summary.stddev:.3f} | {summary.minimum:.3f} | {summary.p50:.3f} | "
            f"{summary.p90:.3f} | {summary.maximum:.3f} |"
        )

    lines.append("")
    lines.append("## Drift Alerts")
    lines.append("")
    if not drift.alerts:
        lines.append("- No threshold breaches detected.")
    else:
        for alert in drift.alerts:
            lines.append(
                f"- {alert.asset_class}/{alert.manager_id}: "
                f"score_delta={alert.score_delta:.3f}, rank_movement={alert.rank_movement}, "
                f"reasons={','.join(alert.reasons)}"
            )

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    baseline = load_entries(args.baseline)
    candidate = baseline if args.candidate is None else load_entries(args.candidate)
    report = render_markdown(
        baseline,
        candidate,
        max_score_delta=args.max_score_delta,
        max_rank_movement=args.max_rank_movement,
    )
    if args.output is None:
        print(report)
    else:
        args.output.write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
