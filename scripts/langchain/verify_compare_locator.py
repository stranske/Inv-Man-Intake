#!/usr/bin/env python3
"""Locate verify:compare non-PASS evidence from verification comment text."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

VERDICT_LINE_RE = re.compile(r"\bverdict\b[^a-z0-9]+(pass|concerns|fail)\b", re.IGNORECASE)
NON_PASS_RE = re.compile(
    r"\b(?:reported non[- ]pass output|verdict[^a-z0-9]+non[- ]pass)\b", re.IGNORECASE
)
PR_LINK_RE = re.compile(
    r"https?://github\.com/[^\s)]+/pull/(\d+)(?:#issuecomment-\d+)?", re.IGNORECASE
)
ISSUE_LINK_RE = re.compile(r"https?://github\.com/[^\s)]+/issues/\d+", re.IGNORECASE)
PR_NUMBER_RE = re.compile(r"\b(?:pr|pull)\s*#?(\d+)\b", re.IGNORECASE)
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


def _extract_verdict(line: str) -> str | None:
    match = VERDICT_LINE_RE.search(line)
    if not match:
        return None
    verdict = _normalize_verdict(match.group(1))
    if verdict == "PASS":
        return None
    return verdict


def _extract_source_links(line: str) -> list[str]:
    links = [match.group(1) for match in MARKDOWN_LINK_RE.finditer(line)]
    links.extend(match.group(0) for match in PR_LINK_RE.finditer(line))
    links.extend(match.group(0) for match in ISSUE_LINK_RE.finditer(line))
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


def _extract_pr_number_from_line(line: str) -> int | None:
    match = PR_NUMBER_RE.search(line)
    if not match:
        return None
    return int(match.group(1))


def extract_non_pass_findings(
    text: str, source_file: str, pr_number: int | None = None
) -> list[VerifyCompareFinding]:
    """Extract non-PASS verdict lines and nearby source URLs from verifier output text."""
    findings: list[VerifyCompareFinding] = []
    recent_links: list[str] = []
    recent_pr: int | None = pr_number
    seen: set[tuple[int | None, str, str, str | None]] = set()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        links = _extract_source_links(line)
        if links:
            recent_links = links
            if recent_pr is None:
                for link in links:
                    link_pr = _extract_pr_number(link)
                    if link_pr is not None:
                        recent_pr = link_pr
                        break

        line_pr = _extract_pr_number_from_line(line)
        if line_pr is not None:
            recent_pr = line_pr

        verdict = _extract_verdict(line)
        if verdict is not None:
            source_url = None
            candidate_pr = pr_number if pr_number is not None else recent_pr
            if recent_links:
                source_url = recent_links[0]
                if candidate_pr is None:
                    candidate_pr = _extract_pr_number(source_url)

            key = (candidate_pr, verdict, line, source_url)
            if key not in seen:
                seen.add(key)
                findings.append(
                    VerifyCompareFinding(
                        pr_number=candidate_pr,
                        verdict=verdict,
                        source_url=source_url,
                        evidence_line=line,
                        source_file=source_file,
                    )
                )

        if NON_PASS_RE.search(line):
            source_url = recent_links[0] if recent_links else None
            candidate_pr = pr_number if pr_number is not None else recent_pr
            key = (candidate_pr, "NON_PASS", line, source_url)
            if key not in seen:
                seen.add(key)
                findings.append(
                    VerifyCompareFinding(
                        pr_number=candidate_pr,
                        verdict="NON_PASS",
                        source_url=source_url,
                        evidence_line=line,
                        source_file=source_file,
                    )
                )

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
        choices=("json", "markdown", "scope"),
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


def _as_scope(findings: list[VerifyCompareFinding], pr_number: int | None = None) -> str:
    if not findings:
        return "No scope can be generated because no non-PASS verify:compare findings were located."

    target = findings[0]
    if pr_number is not None:
        for item in findings:
            if item.pr_number == pr_number:
                target = item
                break

    resolved_pr = target.pr_number if target.pr_number is not None else pr_number
    pr_label = f"PR #{resolved_pr}" if resolved_pr is not None else "target PR"
    source_text = target.source_url or "(link not available)"

    return "\n".join(
        [
            f"## Disposition Scope For {pr_label}",
            "",
            "- Confirm the exact non-PASS evidence line and cite its source link.",
            f"- Evidence link: {source_text}",
            f"- Evidence line: `{target.evidence_line}`",
            "- Decide whether the concern requires a bounded fix PR or documentation-only disposition.",
            "- Keep follow-up limited to verify:compare concerns; do not broaden scope.",
            "- Produce a 2+ sentence rationale for the final disposition decision.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    findings = scan_files(args.files, pr_number=args.pr)

    if args.format == "markdown":
        print(_as_markdown(findings))
    elif args.format == "scope":
        print(_as_scope(findings, pr_number=args.pr))
    else:
        print(json.dumps([asdict(item) for item in findings], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
