#!/usr/bin/env python3
"""Build unresolved PR review thread inventories from saved GitHub API JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _extract_graphql_threads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    root = payload
    if "data" in root and isinstance(root["data"], dict):
        root = root["data"]

    path_candidates = [
        ["repository", "pullRequest", "reviewThreads", "nodes"],
        ["pullRequest", "reviewThreads", "nodes"],
        ["reviewThreads", "nodes"],
    ]
    for path in path_candidates:
        current: Any = root
        for segment in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(segment)
        if isinstance(current, list):
            return [t for t in current if isinstance(t, dict)]
    return []


def _extract_threads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    graphql_threads = _extract_graphql_threads(payload)
    if graphql_threads:
        return graphql_threads

    if isinstance(payload.get("reviewThreads"), list):
        return [t for t in payload["reviewThreads"] if isinstance(t, dict)]

    return []


def _extract_identifier(thread: dict[str, Any]) -> str:
    for key in ("id", "databaseId"):
        value = thread.get(key)
        if value:
            return str(value)

    comments = thread.get("comments")
    nodes = []
    if isinstance(comments, dict):
        nodes = _as_list(comments.get("nodes"))
    elif isinstance(comments, list):
        nodes = comments

    for node in nodes:
        if not isinstance(node, dict):
            continue
        for key in ("databaseId", "id"):
            value = node.get(key)
            if value:
                return f"discussion_r{value}"

    return "unknown-thread-id"


def _extract_url(thread: dict[str, Any]) -> str:
    for key in ("url", "html_url"):
        value = thread.get(key)
        if isinstance(value, str) and value:
            return value

    comments = thread.get("comments")
    nodes = []
    if isinstance(comments, dict):
        nodes = _as_list(comments.get("nodes"))
    elif isinstance(comments, list):
        nodes = comments

    for node in nodes:
        if not isinstance(node, dict):
            continue
        for key in ("url", "html_url"):
            value = node.get(key)
            if isinstance(value, str) and value:
                return value

    return ""


def extract_unresolved_threads(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Return unresolved review threads as `identifier` + `url` pairs."""
    threads = _extract_threads(payload)
    unresolved: list[dict[str, str]] = []

    for thread in threads:
        resolved = thread.get("isResolved")
        if resolved is None:
            resolved = thread.get("resolved")
        if bool(resolved):
            continue

        unresolved.append(
            {
                "identifier": _extract_identifier(thread),
                "url": _extract_url(thread),
            }
        )

    return unresolved


def build_markdown(unresolved: list[dict[str, str]]) -> str:
    lines = [
        "| Thread Identifier | Thread URL |",
        "| --- | --- |",
    ]
    for item in unresolved:
        url = item["url"] or "(missing URL in payload)"
        lines.append(f"| `{item['identifier']}` | {url} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract unresolved review threads from saved GitHub API payloads."
    )
    parser.add_argument("input", type=Path, help="Path to JSON payload containing reviewThreads")
    parser.add_argument("--output", type=Path, help="Write markdown table to this file")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    unresolved = extract_unresolved_threads(payload)
    table = build_markdown(unresolved)

    if args.output:
        args.output.write_text(table + "\n", encoding="utf-8")
    else:
        print(table)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
