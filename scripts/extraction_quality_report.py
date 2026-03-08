#!/usr/bin/env python3
"""Generate extraction QA baseline metrics from fixture corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inv_man_intake.extraction.quality import generate_quality_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("tests/fixtures/extraction/qa_corpus.json"),
        help="Path to the extraction QA corpus JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the JSON report.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    report = generate_quality_report(args.corpus)
    rendered = json.dumps(report, indent=2, sort_keys=True)

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
