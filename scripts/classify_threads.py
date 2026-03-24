#!/usr/bin/env python3
"""Classify unresolved PR review threads as warranted or not-warranted."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("data/pr81_threads.json")
DEFAULT_OUTPUT = Path("data/pr81_threads_classified.json")

Classification = dict[str, str]

NON_FUNCTIONAL_HINTS = (
    "nit",
    "nits",
    "style",
    "readability",
    "wording",
    "rename",
    "naming",
    "comment",
    "doc",
    "docs",
)

FUNCTIONAL_HINTS = (
    "bug",
    "incorrect",
    "break",
    "regression",
    "error",
    "failing",
    "missing",
    "security",
    "validation",
    "edge case",
    "null",
)


def _thread_text(thread: Mapping[str, Any]) -> str:
    comments = thread.get("comments")
    if not isinstance(comments, list):
        return ""
    parts: list[str] = []
    for item in comments:
        if isinstance(item, Mapping):
            body = item.get("body")
            if isinstance(body, str):
                parts.append(body)
    return "\n".join(parts).strip()


def classify_thread(thread: Mapping[str, Any]) -> Classification:
    """Return classification and rationale for a single thread."""
    text = _thread_text(thread).lower()
    if not text:
        return {
            "classification": "warranted",
            "rationale": "No comment text was available, so defaulting to warranted for manual follow-up.",
        }

    if any(token in text for token in FUNCTIONAL_HINTS):
        return {
            "classification": "warranted",
            "rationale": "Thread appears to describe correctness, reliability, or validation risk.",
        }

    if any(token in text for token in NON_FUNCTIONAL_HINTS):
        return {
            "classification": "not-warranted",
            "rationale": "Thread appears focused on style or wording without clear functional impact.",
        }

    return {
        "classification": "warranted",
        "rationale": "Thread impact is ambiguous; defaulting to warranted for conservative triage.",
    }


def classify_threads_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Attach classification fields to each thread in the source document."""
    threads = document.get("threads")
    if not isinstance(threads, list):
        raise ValueError("Input document must contain a list under 'threads'")

    enriched_threads: list[dict[str, Any]] = []
    for thread in threads:
        if not isinstance(thread, Mapping):
            continue
        enriched = dict(thread)
        enriched.update(classify_thread(thread))
        enriched_threads.append(enriched)

    output = dict(document)
    output["threads"] = enriched_threads
    output["classified_thread_count"] = len(enriched_threads)
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    document = json.loads(args.input.read_text(encoding="utf-8"))
    classified = classify_threads_document(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(classified, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote classified thread output to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
