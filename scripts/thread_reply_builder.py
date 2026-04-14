#!/usr/bin/env python3
"""Build ready-to-post PR review thread replies from an unresolved-thread inventory markdown."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ThreadDisposition:
    thread_url: str
    discussion_id: str
    classification: str
    rationale: str
    disposition: str


def _ensure_sentence(text: str, *, field_name: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        raise ValueError(f"{field_name} must not be empty")
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def _extract_discussion_id(url: str) -> str:
    match = re.search(r"#(discussion_r\d+)", url)
    if not match:
        raise ValueError(f"thread URL is missing a discussion id fragment: {url}")
    return match.group(1)


def parse_thread_inventory(markdown: str) -> list[ThreadDisposition]:
    """Parse the markdown inventory table into normalized thread disposition rows."""
    rows = re.findall(
        r"^\|\s*(https?://[^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$",
        markdown,
        flags=re.MULTILINE,
    )

    dispositions: list[ThreadDisposition] = []
    for thread_url, classification, rationale, disposition in rows:
        normalized_class = classification.strip().lower()
        if normalized_class not in {"warranted-fix", "not-warranted"}:
            continue

        dispositions.append(
            ThreadDisposition(
                thread_url=thread_url.strip(),
                discussion_id=_extract_discussion_id(thread_url.strip()),
                classification=normalized_class,
                rationale=_ensure_sentence(rationale, field_name="rationale"),
                disposition=_ensure_sentence(disposition, field_name="disposition"),
            )
        )

    return dispositions


def build_thread_reply(item: ThreadDisposition) -> str:
    """Render one thread reply that satisfies keepalive acceptance criteria."""
    if item.classification == "warranted-fix":
        if not re.search(r"(https?://|#\d+|`[0-9a-f]{7,40}`)", item.disposition):
            raise ValueError(
                f"warranted-fix disposition for {item.discussion_id} must include a PR/commit reference"
            )
        return item.disposition

    return f"This change is not warranted because {item.rationale[0].lower() + item.rationale[1:]}"


def render_replies_markdown(items: list[ThreadDisposition]) -> str:
    lines = ["## Thread Reply Drafts", ""]
    for item in items:
        lines.append(f"- `{item.discussion_id}`: {build_thread_reply(item)}")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True, help="Inventory markdown path")
    parser.add_argument(
        "--output", type=Path, required=True, help="Reply draft markdown output path"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    content = args.inventory.read_text(encoding="utf-8")
    dispositions = parse_thread_inventory(content)
    if not dispositions:
        raise ValueError("no unresolved thread dispositions found in inventory markdown")

    output = render_replies_markdown(dispositions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
