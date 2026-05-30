"""Headless ``inv-man-ingest`` console entry point.

Runs the deterministic intake-to-scoring pipeline for one intake bundle and
writes ``run.json`` plus the named artifact files to an output directory.

Invocation forms (both supported):

    inv-man-ingest <bundle.json> --out <output_dir>
    python -m inv_man_intake.cli.ingest <bundle.json> --out <output_dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from inv_man_intake.run import RunResult, run_pipeline


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inv-man-ingest",
        description=(
            "Run the deterministic intake-to-scoring pipeline headlessly and write "
            "run.json plus named artifacts to an output directory (zero data egress)."
        ),
    )
    parser.add_argument("bundle", help="Path to the intake bundle JSON file.")
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for run.json and the named artifact files.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ingest pipeline. Returns 0 on success, non-zero on failure."""

    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    bundle_path = Path(args.bundle)
    output_dir = Path(args.out)

    if not bundle_path.is_file():
        print(f"error: intake bundle not found: {bundle_path}", file=sys.stderr)
        return 2

    try:
        result = run_pipeline(bundle_path, output_dir=output_dir)
    except (ValueError, KeyError, json.JSONDecodeError, OSError) as exc:
        print(f"error: intake run failed: {exc}", file=sys.stderr)
        return 1

    _print_summary(result=result, output_dir=output_dir)
    return 0


def _print_summary(*, result: RunResult, output_dir: Path) -> None:
    print(f"run_id: {result.run_id}")
    print(f"final_score: {result.final_score}")
    print(f"escalation: {result.escalation_state.get('reason')}")
    print(f"output_dir: {output_dir}")
    for ref in result.artifact_refs:
        print(f"artifact: {output_dir / ref}")


if __name__ == "__main__":  # pragma: no cover - module CLI shim
    raise SystemExit(main())
