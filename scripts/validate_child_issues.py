#!/usr/bin/env python3
"""Validate child issues for required AGENT_ISSUE_TEMPLATE sections."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_OWNER = "stranske"
DEFAULT_REPO = "Inv-Man-Intake"
DEFAULT_START_ISSUE = 8
DEFAULT_END_ISSUE = 15
REQUIRED_SECTIONS = (
    "Why",
    "Scope",
    "Non-Goals",
    "Tasks",
    "Acceptance Criteria",
    "Implementation Notes",
)


@dataclass(frozen=True)
class IssueValidationResult:
    issue_number: int
    missing_sections: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_sections


def _build_section_pattern(section: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*##\s+{re.escape(section)}\s*$", re.MULTILINE)


def validate_issue_body(issue_number: int, issue_body: str) -> IssueValidationResult:
    missing = tuple(
        section
        for section in REQUIRED_SECTIONS
        if not _build_section_pattern(section).search(issue_body)
    )
    return IssueValidationResult(issue_number=issue_number, missing_sections=missing)


def _candidate_local_paths(issues_dir: Path, issue_number: int) -> tuple[Path, ...]:
    return (
        issues_dir / f"issue-{issue_number}.md",
        issues_dir / f"issue-{issue_number}.txt",
        issues_dir / f"issue-{issue_number}.yml",
        issues_dir / f"{issue_number}.md",
        issues_dir / f"{issue_number}.txt",
    )


def _load_issue_body_from_directory(issues_dir: Path, issue_number: int) -> str:
    for path in _candidate_local_paths(issues_dir, issue_number):
        if path.is_file():
            return path.read_text(encoding="utf-8")
    candidates = ", ".join(
        str(path.name) for path in _candidate_local_paths(issues_dir, issue_number)
    )
    raise FileNotFoundError(
        f"Issue #{issue_number} was not found in {issues_dir}. Expected one of: {candidates}"
    )


def _fetch_issue_json(
    owner: str, repo: str, issue_number: int, token: str | None
) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "inv-man-intake-issue-validator",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url=url, headers=headers)
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed GitHub API URL
        return json.loads(response.read().decode("utf-8"))


def _load_issue_body_from_github(
    owner: str, repo: str, issue_number: int, token: str | None
) -> str:
    issue = _fetch_issue_json(owner=owner, repo=repo, issue_number=issue_number, token=token)
    if "pull_request" in issue:
        raise ValueError(f"#{issue_number} is a pull request, not an issue")
    return str(issue.get("body") or "")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate child issues for required AGENT_ISSUE_TEMPLATE sections."
    )
    parser.add_argument(
        "--owner", default=DEFAULT_OWNER, help=f"GitHub owner (default: {DEFAULT_OWNER})"
    )
    parser.add_argument(
        "--repo", default=DEFAULT_REPO, help=f"GitHub repo (default: {DEFAULT_REPO})"
    )
    parser.add_argument(
        "--start-issue",
        type=int,
        default=DEFAULT_START_ISSUE,
        help=f"First issue number in range (default: {DEFAULT_START_ISSUE})",
    )
    parser.add_argument(
        "--end-issue",
        type=int,
        default=DEFAULT_END_ISSUE,
        help=f"Last issue number in range (default: {DEFAULT_END_ISSUE})",
    )
    parser.add_argument(
        "--issues-dir",
        type=Path,
        default=None,
        help="Local directory containing issue body files for offline validation.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token (defaults to GITHUB_TOKEN env var if set).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.start_issue > args.end_issue:
        print("--start-issue must be <= --end-issue", file=sys.stderr)
        return 2

    issue_numbers = range(args.start_issue, args.end_issue + 1)
    validations: list[IssueValidationResult] = []

    print(
        f"Validating issue sections for #{args.start_issue}-#{args.end_issue} "
        f"({'local files' if args.issues_dir else f'{args.owner}/{args.repo}'})"
    )

    for issue_number in issue_numbers:
        try:
            if args.issues_dir:
                body = _load_issue_body_from_directory(args.issues_dir, issue_number)
            else:
                body = _load_issue_body_from_github(
                    owner=args.owner,
                    repo=args.repo,
                    issue_number=issue_number,
                    token=args.token,
                )
        except (FileNotFoundError, ValueError, HTTPError, URLError) as exc:
            print(f"ERROR: Unable to load issue #{issue_number}: {exc}", file=sys.stderr)
            return 2

        result = validate_issue_body(issue_number, body)
        validations.append(result)

    failures = [result for result in validations if not result.is_valid]
    if failures:
        print("\nMissing required sections detected:")
        for failure in failures:
            missing = ", ".join(failure.missing_sections)
            print(f"- #{failure.issue_number}: {missing}")
        return 1

    print("\nAll issues contain required sections:")
    for issue_number in issue_numbers:
        print(f"- #{issue_number}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
