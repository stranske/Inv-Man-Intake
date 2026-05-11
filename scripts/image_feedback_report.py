#!/usr/bin/env python3
"""Generate visual-artifact feedback summary exports."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inv_man_intake.data.repository import VisualArtifactRepository
from inv_man_intake.images.feedback_report import (
    generate_feedback_summary_report,
    render_feedback_summary_csv,
    render_feedback_summary_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        required=True,
        help="SQLite database containing visual_artifact_feedback.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "csv"),
        default="json",
        help="Export format.",
    )
    parser.add_argument(
        "--reviewed-from",
        default=None,
        help="Inclusive ISO-8601 lower bound for reviewed_at.",
    )
    parser.add_argument(
        "--reviewed-to",
        default=None,
        help="Inclusive ISO-8601 upper bound for reviewed_at.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file. Defaults to stdout.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    with sqlite3.connect(args.database) as connection:
        repository = VisualArtifactRepository(connection)
        report = generate_feedback_summary_report(
            repository,
            generated_at=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            reviewed_from=args.reviewed_from,
            reviewed_to=args.reviewed_to,
        )

    rendered = (
        render_feedback_summary_json(report)
        if args.format == "json"
        else render_feedback_summary_csv(report)
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
