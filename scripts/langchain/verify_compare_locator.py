#!/usr/bin/env python3
"""Locate verify:compare non-PASS evidence from verification comment text."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

VERDICT_RE = re.compile(r"\b(pass|concerns|fail)\b", re.IGNORECASE)
PR_LINK_RE = re.compile(
    r"https?://github\.com/[^\s)]+/pull/(\d+)(?:#issuecomment-\d+)?", re.IGNORECASE
)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^)]+)\)")


@dataclass(frozen=True)
class VerifyCompareFinding:
    """Structured non-PASS evidence extracted from verification comments."""

    pr_number: int | None
    verdict: str
    source_url: str | None
    evidence_line: str
    source_file: str


def _normalize_verdict(token: str) -> str:
    value = token.strip().upper()
    return "CONCERNS" if value.startswith("CONCERN") else value


def _extract_source_links(line: str) -> list[str]:
    links = [match.group(1) for match in MARKDOWN_LINK_RE.finditer(line)]
    links.extend(match.group(0) for match in PR_LINK_RE.finditer(line))
    deduped: list[str] = []
    for url in links:
        if url not in deduped:
            deduped.append(url)
    return deduped


def _extract_pr_number(url: str) -> int | None:
    match = PR_LINK_RE.search(url)
    if not match:
        return None
    return int(match.group(1))


def extract_non_pass_findings(
    text: str, source_file: str, pr_number: int | None = None
) -> list[VerifyCompareFinding]:
    """Extract non-PASS verdict lines and nearby source URLs from verifier output text."""
    findings: list[VerifyCompareFinding] = []
    recent_links: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        links = _extract_source_links(line)
        if links:
            recent_links = links

        for match in VERDICT_RE.finditer(line):
            verdict = _normalize_verdict(match.group(1))
            if verdict == "PASS":
                continue

            source_url = None
            candidate_pr = pr_number
            if recent_links:
                source_url = recent_links[0]
                if candidate_pr is None:
                    candidate_pr = _extract_pr_number(source_url)

            findings.append(
                VerifyCompareFinding(
                    pr_number=candidate_pr,
                    verdict=verdict,
                    source_url=source_url,
                    evidence_line=line,
                    source_file=source_file,
                )
            )
            break

    if pr_number is None:
        return findings
    return [item for item in findings if item.pr_number == pr_number]


def scan_files(paths: Iterable[Path], pr_number: int | None = None) -> list[VerifyCompareFinding]:
    """Scan text files and return all extracted non-PASS findings."""
    findings: list[VerifyCompareFinding] = []
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(extract_non_pass_findings(text, source_file=str(path), pr_number=pr_number))
    return findings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Locate verify:compare non-PASS output in text files."
    )
    parser.add_argument("files", nargs="+", type=Path, help="Input text files to scan")
    parser.add_argument("--pr", type=int, default=None, help="Limit results to this PR number")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format",
    )
    return parser


def _as_markdown(findings: list[VerifyCompareFinding]) -> str:
    if not findings:
        return "No non-PASS verify:compare findings located."

    lines = ["| PR | Verdict | Source | Evidence | File |", "| --- | --- | --- | --- | --- |"]
    for item in findings:
        pr_text = str(item.pr_number) if item.pr_number is not None else "unknown"
        source_text = item.source_url or "(no source link)"
        evidence = item.evidence_line.replace("|", "\\|")
        lines.append(
            f"| {pr_text} | {item.verdict} | {source_text} | {evidence} | {item.source_file} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    findings = scan_files(args.files, pr_number=args.pr)

    if args.format == "markdown":
        print(_as_markdown(findings))
    else:
        print(json.dumps([asdict(item) for item in findings], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
