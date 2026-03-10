#!/usr/bin/env python3
"""Generate a markdown classification report for PR review threads."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("data/pr81_threads_classified.json")
DEFAULT_OUTPUT = Path("data/pr81_threads_report.md")


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def generate_markdown_table(document: Mapping[str, Any]) -> str:
    """Build markdown report with required columns: Thread ID, Classification, Rationale."""
    lines = [
        "| Thread ID | Classification | Rationale |",
        "|---|---|---|",
    ]
    threads = document.get("threads")
    if not isinstance(threads, list):
        return "\n".join(lines) + "\n"

    for thread in threads:
        if not isinstance(thread, Mapping):
            continue
        thread_id = _escape_cell(str(thread.get("thread_id", "")))
        classification = _escape_cell(str(thread.get("classification", "")))
        rationale = _escape_cell(str(thread.get("rationale", "")))
        lines.append(f"| {thread_id} | {classification} | {rationale} |")

    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    document = json.loads(args.input.read_text(encoding="utf-8"))
    report = generate_markdown_table(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote markdown report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
