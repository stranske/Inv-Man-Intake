#!/usr/bin/env python3
"""Validate that each classified thread has non-empty classification and rationale."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("data/pr81_threads_classified.json")


def find_invalid_threads(document: Mapping[str, Any]) -> list[str]:
    """Return thread ids that are missing classification or rationale."""
    invalid: list[str] = []
    threads = document.get("threads")
    if not isinstance(threads, list):
        return ["<document.threads>"]

    for thread in threads:
        if not isinstance(thread, Mapping):
            invalid.append("<non-object-thread>")
            continue
        thread_id = str(thread.get("thread_id", "<missing-thread-id>"))
        classification = str(thread.get("classification", "")).strip()
        rationale = str(thread.get("rationale", "")).strip()
        if not classification or not rationale:
            invalid.append(thread_id)
    return invalid


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    document = json.loads(args.input.read_text(encoding="utf-8"))
    invalid = find_invalid_threads(document)
    if invalid:
        print(
            "Classification output validation failed for thread(s): " + ", ".join(invalid),
            file=sys.stderr,
        )
        return 1

    print("Classification output validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
