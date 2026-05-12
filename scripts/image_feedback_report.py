#!/usr/bin/env python3
"""Generate visual-artifact feedback summary exports."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
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
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=None,
        help=(
            "Optional output directory for schedule/manual bundles. "
            "Writes both JSON and CSV exports with generated-at timestamp names."
        ),
    )
    parser.add_argument(
        "--scheduled-daily",
        action="store_true",
        help=(
            "Run in scheduled mode with bundle output and a default 24-hour review window "
            "ending at generated_at unless reviewed-from/reviewed-to are explicitly provided."
        ),
    )
    return parser


def _parse_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def main() -> int:
    args = build_parser().parse_args()
    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    reviewed_from = args.reviewed_from
    reviewed_to = args.reviewed_to

    if args.scheduled_daily:
        if args.bundle_dir is None:
            raise SystemExit("--scheduled-daily requires --bundle-dir")
        window_end = _parse_iso8601(reviewed_to) if reviewed_to else _parse_iso8601(generated_at)
        if reviewed_from is None:
            reviewed_from = (window_end - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
        if reviewed_to is None:
            reviewed_to = window_end.isoformat().replace("+00:00", "Z")

    with sqlite3.connect(args.database) as connection:
        repository = VisualArtifactRepository(connection)
        report = generate_feedback_summary_report(
            repository,
            generated_at=generated_at,
            reviewed_from=reviewed_from,
            reviewed_to=reviewed_to,
        )

    if args.bundle_dir is not None:
        bundle_stamp = report.generated_at.replace(":", "").replace("-", "")
        args.bundle_dir.mkdir(parents=True, exist_ok=True)
        (args.bundle_dir / f"image-feedback-{bundle_stamp}.json").write_text(
            render_feedback_summary_json(report),
            encoding="utf-8",
        )
        (args.bundle_dir / f"image-feedback-{bundle_stamp}.csv").write_text(
            render_feedback_summary_csv(report),
            encoding="utf-8",
        )
        return 0

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
