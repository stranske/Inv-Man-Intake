#!/usr/bin/env python3
"""Generate visual artifact feedback summary export for tuning workflows.

Reads feedback records from a SQLite database and produces a CSV or JSON
report with key metrics: informative rate, rank distribution, and disagreement
rate across all reviewers.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inv_man_intake.data.provenance import VisualArtifactFeedbackRecord
from inv_man_intake.images.report import aggregate_feedback, render_csv, render_json


def _load_feedback(
    conn: sqlite3.Connection,
    timestamp_from: str | None,
    timestamp_to: str | None,
) -> list[VisualArtifactFeedbackRecord]:
    query = (
        "SELECT artifact_id, is_informative, quality_rank, reviewer, reviewed_at, notes "
        "FROM visual_artifact_feedback"
    )
    params: list[str] = []
    conditions: list[str] = []
    if timestamp_from is not None:
        conditions.append("reviewed_at >= ?")
        params.append(timestamp_from)
    if timestamp_to is not None:
        conditions.append("reviewed_at <= ?")
        params.append(timestamp_to)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY reviewed_at ASC, artifact_id ASC, reviewer ASC"

    rows = conn.execute(query, params).fetchall()
    return [
        VisualArtifactFeedbackRecord(
            artifact_id=str(row[0]),
            is_informative=bool(row[1]),
            quality_rank=int(row[2]),
            reviewer=str(row[3]),
            reviewed_at=str(row[4]),
            notes=None if row[5] is None else str(row[5]),
        )
        for row in rows
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to the SQLite database containing visual_artifact_feedback records.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        dest="output_format",
        help="Output format (default: json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write output to this file instead of stdout.",
    )
    parser.add_argument(
        "--from",
        dest="timestamp_from",
        default=None,
        help="Include only feedback reviewed at or after this ISO-8601 UTC timestamp.",
    )
    parser.add_argument(
        "--to",
        dest="timestamp_to",
        default=None,
        help="Include only feedback reviewed at or before this ISO-8601 UTC timestamp.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.db.exists():
        print(f"error: database not found: {args.db}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(args.db))
    try:
        records = _load_feedback(conn, args.timestamp_from, args.timestamp_to)
    except sqlite3.OperationalError as exc:
        print(f"error: could not read feedback records: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    summary = aggregate_feedback(records, args.timestamp_from, args.timestamp_to)
    rendered = render_json(summary) if args.output_format == "json" else render_csv(summary)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8"
        )
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
