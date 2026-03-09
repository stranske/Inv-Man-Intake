#!/usr/bin/env python3
"""Build a disposition document from verify:compare output text."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Concern:
    text: str
    reference: str


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -:\n\t")


def extract_concerns(report_text: str, default_reference: str) -> list[Concern]:
    """Extract concern strings from verify:compare markdown-like text."""
    concerns: list[Concern] = []

    heading_match = re.search(
        r"###\s*Concerns\s*\n([\s\S]*?)(?=###|##|$)", report_text, re.IGNORECASE
    )
    if heading_match:
        for line in heading_match.group(1).splitlines():
            line = line.strip()
            if line.startswith("- "):
                text = _clean_text(line[2:])
                if len(text) >= 8:
                    concerns.append(Concern(text=text, reference=default_reference))

    for block in re.findall(r"-\s+\*\*Concerns:\*\*\s*\n((?:\s+-\s+.+\n?)*)", report_text):
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("- "):
                text = _clean_text(line[2:])
                if len(text) >= 8:
                    concerns.append(Concern(text=text, reference=default_reference))

    for line in report_text.splitlines():
        line = line.strip()
        if not line.lower().startswith("- concern:"):
            continue
        text = _clean_text(line.split(":", 1)[1])
        if len(text) >= 8:
            concerns.append(Concern(text=text, reference=default_reference))

    unique: list[Concern] = []
    seen: set[str] = set()
    for concern in concerns:
        key = concern.text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(concern)
    return unique


def render_disposition_markdown(
    *,
    pr_number: int,
    pr_url: str,
    source_reference_url: str,
    concerns: list[Concern],
) -> str:
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    lines = [
        f"# PR #{pr_number} verify:compare disposition",
        "",
        f"- PR: {pr_url}",
        f"- verify:compare output reference: {source_reference_url}",
        f"- Generated (UTC): {generated_at}",
        "",
        "## Concerns and Disposition",
        "",
        "| Concern | verify:compare output reference | Disposition decision |",
        "|---|---|---|",
    ]

    if concerns:
        for concern in concerns:
            safe_text = concern.text.replace("|", "\\|")
            lines.append(
                f"| {safe_text} | {concern.reference} | "
                "requires follow-up to address [specific change] |"
            )
    else:
        lines.append(
            "| No concerns could be extracted from provided verify:compare output text. | "
            f"{source_reference_url} | "
            "requires follow-up to address [specific change: provide raw verify:compare output] |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Update each disposition to either:",
            "  - `not warranted because [reason]`",
            "  - `requires follow-up to address [specific change]`",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="Path to raw verify:compare output text."
    )
    parser.add_argument("--output", type=Path, required=True, help="Output markdown path.")
    parser.add_argument("--pr-number", type=int, required=True, help="PR number.")
    parser.add_argument("--pr-url", required=True, help="PR URL.")
    parser.add_argument(
        "--source-reference-url",
        required=True,
        help="URL that points directly to the verify:compare output.",
    )
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args()
    raw_text = args.input.read_text(encoding="utf-8")
    concerns = extract_concerns(raw_text, default_reference=args.source_reference_url)
    output = render_disposition_markdown(
        pr_number=args.pr_number,
        pr_url=args.pr_url,
        source_reference_url=args.source_reference_url,
        concerns=concerns,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
