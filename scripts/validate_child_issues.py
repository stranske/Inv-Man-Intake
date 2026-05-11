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
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_OWNER = "stranske"
DEFAULT_REPO = "Inv-Man-Intake"
DEFAULT_EPIC_ISSUE = 7
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


@dataclass(frozen=True)
class EpicTaskLinksValidationResult:
    epic_issue_number: int
    missing_issue_links: tuple[int, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_issue_links


def render_epic_task_links_checklist(
    owner: str, repo: str, start_issue: int, end_issue: int
) -> str:
    """Render markdown checklist lines for child issue links used in epic Tasks sections."""
    return "\n".join(
        f"- [ ] [#{issue_number}]({_issue_url(owner, repo, issue_number)})"
        for issue_number in range(start_issue, end_issue + 1)
    )


def render_epic_tasks_section(owner: str, repo: str, start_issue: int, end_issue: int) -> str:
    """Render a complete ## Tasks section for epic issue bodies."""
    checklist = render_epic_task_links_checklist(
        owner=owner,
        repo=repo,
        start_issue=start_issue,
        end_issue=end_issue,
    )
    return f"## Tasks\n{checklist}"


def _build_section_pattern(section: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*##\s+{re.escape(section)}\s*$", re.MULTILINE)


def validate_issue_body(issue_number: int, issue_body: str) -> IssueValidationResult:
    missing = tuple(
        section
        for section in REQUIRED_SECTIONS
        if not _build_section_pattern(section).search(issue_body)
    )
    return IssueValidationResult(issue_number=issue_number, missing_sections=missing)


def _extract_tasks_section(markdown_body: str) -> str:
    bounds = _tasks_section_bounds(markdown_body)
    if bounds is None:
        return ""
    section_start, section_end = bounds
    return markdown_body[section_start:section_end]


def _tasks_section_bounds(markdown_body: str) -> tuple[int, int] | None:
    match = re.search(r"^\s*##\s+Tasks\s*$", markdown_body, re.MULTILINE)
    if not match:
        return None

    section_start = match.end()
    section_end_match = re.search(r"^\s*##\s+\S", markdown_body[section_start:], re.MULTILINE)
    if section_end_match:
        section_end = section_start + section_end_match.start()
        return section_start, section_end
    return section_start, len(markdown_body)


def _issue_url(owner: str, repo: str, issue_number: int) -> str:
    return f"https://github.com/{owner}/{repo}/issues/{issue_number}"


def _contains_exact_issue_url(body: str, owner: str, repo: str, issue_number: int) -> bool:
    issue_url = _issue_url(owner, repo, issue_number)
    return re.search(rf"{re.escape(issue_url)}(?!\d)", body) is not None


def _contains_task_markdown_issue_link(body: str, owner: str, repo: str, issue_number: int) -> bool:
    issue_url = _issue_url(owner, repo, issue_number)
    link_pattern = re.compile(
        rf"\[[^\]]*#{issue_number}[^\]]*\]\(\s*{re.escape(issue_url)}\s*\)",
        re.IGNORECASE,
    )
    return link_pattern.search(body) is not None


def validate_epic_task_links(
    epic_issue_number: int,
    epic_issue_body: str,
    owner: str,
    repo: str,
    start_issue: int,
    end_issue: int,
) -> EpicTaskLinksValidationResult:
    tasks_section = _extract_tasks_section(epic_issue_body)
    missing_issue_links = tuple(
        issue_number
        for issue_number in range(start_issue, end_issue + 1)
        if not _contains_task_markdown_issue_link(tasks_section, owner, repo, issue_number)
    )
    return EpicTaskLinksValidationResult(
        epic_issue_number=epic_issue_number,
        missing_issue_links=missing_issue_links,
    )


def ensure_epic_task_links(
    epic_issue_body: str,
    owner: str,
    repo: str,
    start_issue: int,
    end_issue: int,
    create_tasks_section_if_missing: bool = False,
) -> tuple[str, tuple[int, ...]]:
    """Insert missing child-issue links into the epic issue's ## Tasks section."""
    bounds = _tasks_section_bounds(epic_issue_body)
    if bounds is None:
        if not create_tasks_section_if_missing:
            raise ValueError("Epic issue body does not contain a ## Tasks section")
        section = render_epic_tasks_section(
            owner=owner,
            repo=repo,
            start_issue=start_issue,
            end_issue=end_issue,
        )
        normalized_body = epic_issue_body.rstrip()
        if normalized_body:
            normalized_body = f"{normalized_body}\n\n{section}\n"
        else:
            normalized_body = f"{section}\n"
        return normalized_body, tuple(range(start_issue, end_issue + 1))

    section_start, section_end = bounds
    tasks_section = epic_issue_body[section_start:section_end]
    missing_issue_links = tuple(
        issue_number
        for issue_number in range(start_issue, end_issue + 1)
        if not _contains_task_markdown_issue_link(tasks_section, owner, repo, issue_number)
    )
    if not missing_issue_links:
        return epic_issue_body, ()

    append_lines = "\n".join(
        f"- [ ] [#{issue_number}]({_issue_url(owner, repo, issue_number)})"
        for issue_number in missing_issue_links
    )

    updated_tasks = tasks_section
    if updated_tasks and not updated_tasks.endswith("\n"):
        updated_tasks += "\n"
    updated_tasks += append_lines + "\n"

    updated_body = epic_issue_body[:section_start] + updated_tasks + epic_issue_body[section_end:]
    return updated_body, missing_issue_links


def _candidate_local_paths(issues_dir: Path, issue_number: int) -> tuple[Path, ...]:
    return (
        issues_dir / f"issue-{issue_number}.md",
        issues_dir / f"issue-{issue_number}.txt",
        issues_dir / f"issue-{issue_number}.yml",
        issues_dir / f"{issue_number}.md",
        issues_dir / f"{issue_number}.txt",
    )


def _load_issue_body_from_directory(issues_dir: Path, issue_number: int) -> str:
    issue_path = _resolve_issue_path_from_directory(issues_dir, issue_number)
    if issue_path is None:
        candidates = ", ".join(
            str(path.name) for path in _candidate_local_paths(issues_dir, issue_number)
        )
        raise FileNotFoundError(
            f"Issue #{issue_number} was not found in {issues_dir}. Expected one of: {candidates}"
        )
    return issue_path.read_text(encoding="utf-8")


def _resolve_issue_path_from_directory(issues_dir: Path, issue_number: int) -> Path | None:
    for path in _candidate_local_paths(issues_dir, issue_number):
        if path.is_file():
            return path
    return None


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
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected GitHub API response for issue #{issue_number}")
    return cast(dict[str, Any], payload)


def _patch_issue_body_on_github(
    owner: str, repo: str, issue_number: int, body: str, token: str | None
) -> None:
    if not token:
        raise ValueError("GitHub token is required to update remote issue bodies")

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    payload = json.dumps({"body": body}).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "inv-man-intake-issue-validator",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    request = Request(url=url, data=payload, headers=headers, method="PATCH")
    with urlopen(request, timeout=30):  # noqa: S310 - fixed GitHub API URL
        return


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
        "--epic-body-file",
        type=Path,
        default=None,
        help=(
            "Path to a local markdown file containing the epic issue body. "
            "Used for --check-epic-task-links / --fix-epic-task-links."
        ),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token (defaults to GITHUB_TOKEN env var if set).",
    )
    parser.add_argument(
        "--epic-issue",
        type=int,
        default=DEFAULT_EPIC_ISSUE,
        help=(
            "Epic issue number to validate for child issue links in the Tasks section "
            f"(default: {DEFAULT_EPIC_ISSUE})."
        ),
    )
    parser.add_argument(
        "--check-epic-task-links",
        action="store_true",
        help=(
            "Validate that the epic issue's ## Tasks section contains links to every child issue "
            "in the configured issue range."
        ),
    )
    parser.add_argument(
        "--epic-links-only",
        action="store_true",
        help=(
            "Only validate/fix epic task links and skip child issue section validation for "
            f"#{DEFAULT_START_ISSUE}-#{DEFAULT_END_ISSUE}."
        ),
    )
    parser.add_argument(
        "--fix-epic-task-links",
        action="store_true",
        help=(
            "When epic links are missing, add checklist links for the configured issue range to "
            "the epic issue in --issues-dir."
        ),
    )
    parser.add_argument(
        "--create-missing-tasks-section",
        action="store_true",
        help=(
            "When used with --fix-epic-task-links, create a ## Tasks section if the epic body "
            "does not already contain one."
        ),
    )
    parser.add_argument(
        "--print-epic-task-links-checklist",
        action="store_true",
        help=(
            "Print a markdown checklist snippet with links for each child issue in the configured "
            "issue range, then exit."
        ),
    )
    parser.add_argument(
        "--print-epic-tasks-section",
        action="store_true",
        help=(
            "Print a complete ## Tasks section containing checklist links for the configured issue "
            "range, then exit."
        ),
    )
    parser.add_argument(
        "--print-fixed-epic-body",
        action="store_true",
        help=(
            "When --check-epic-task-links finds missing links, print the fully patched epic body "
            "to stdout to simplify manual issue updates."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.start_issue > args.end_issue:
        print("--start-issue must be <= --end-issue", file=sys.stderr)
        return 2
    if args.epic_body_file and not args.epic_body_file.is_file():
        print(f"--epic-body-file does not exist: {args.epic_body_file}", file=sys.stderr)
        return 2
    if args.epic_body_file and not (args.check_epic_task_links or args.fix_epic_task_links):
        print(
            "--epic-body-file requires --check-epic-task-links or --fix-epic-task-links",
            file=sys.stderr,
        )
        return 2
    if args.print_fixed_epic_body and not args.check_epic_task_links:
        print("--print-fixed-epic-body requires --check-epic-task-links", file=sys.stderr)
        return 2
    if args.epic_links_only and not args.check_epic_task_links:
        print("--epic-links-only requires --check-epic-task-links", file=sys.stderr)
        return 2
    if args.print_epic_task_links_checklist:
        print(
            render_epic_task_links_checklist(
                owner=args.owner,
                repo=args.repo,
                start_issue=args.start_issue,
                end_issue=args.end_issue,
            )
        )
        return 0
    if args.print_epic_tasks_section:
        print(
            render_epic_tasks_section(
                owner=args.owner,
                repo=args.repo,
                start_issue=args.start_issue,
                end_issue=args.end_issue,
            )
        )
        return 0

    issue_numbers = range(args.start_issue, args.end_issue + 1)
    if not args.epic_links_only:
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

    if args.check_epic_task_links:
        try:
            if args.epic_body_file:
                epic_body = args.epic_body_file.read_text(encoding="utf-8")
            elif args.issues_dir:
                epic_body = _load_issue_body_from_directory(args.issues_dir, args.epic_issue)
            else:
                epic_body = _load_issue_body_from_github(
                    owner=args.owner,
                    repo=args.repo,
                    issue_number=args.epic_issue,
                    token=args.token,
                )
        except (FileNotFoundError, ValueError, HTTPError, URLError) as exc:
            print(f"ERROR: Unable to load epic issue #{args.epic_issue}: {exc}", file=sys.stderr)
            return 2

        epic_result = validate_epic_task_links(
            epic_issue_number=args.epic_issue,
            epic_issue_body=epic_body,
            owner=args.owner,
            repo=args.repo,
            start_issue=args.start_issue,
            end_issue=args.end_issue,
        )
        if not epic_result.is_valid:
            if args.print_fixed_epic_body:
                try:
                    fixed_body, _ = ensure_epic_task_links(
                        epic_issue_body=epic_body,
                        owner=args.owner,
                        repo=args.repo,
                        start_issue=args.start_issue,
                        end_issue=args.end_issue,
                    )
                except ValueError as exc:
                    print(f"ERROR: Unable to render fixed epic issue body: {exc}", file=sys.stderr)
                    return 2
                print("\n--- BEGIN FIXED EPIC BODY ---")
                print(fixed_body)
                print("--- END FIXED EPIC BODY ---")
            if args.fix_epic_task_links:
                fixed_body, added_issue_links = ensure_epic_task_links(
                    epic_issue_body=epic_body,
                    owner=args.owner,
                    repo=args.repo,
                    start_issue=args.start_issue,
                    end_issue=args.end_issue,
                    create_tasks_section_if_missing=args.create_missing_tasks_section,
                )
                if args.epic_body_file:
                    args.epic_body_file.write_text(fixed_body, encoding="utf-8")
                elif args.issues_dir:
                    epic_path = _resolve_issue_path_from_directory(args.issues_dir, args.epic_issue)
                    if epic_path is None:
                        print(
                            f"ERROR: Unable to locate epic issue #{args.epic_issue} for update "
                            f"in {args.issues_dir}",
                            file=sys.stderr,
                        )
                        return 2
                    epic_path.write_text(fixed_body, encoding="utf-8")
                else:
                    try:
                        _patch_issue_body_on_github(
                            owner=args.owner,
                            repo=args.repo,
                            issue_number=args.epic_issue,
                            body=fixed_body,
                            token=args.token,
                        )
                    except (ValueError, HTTPError, URLError) as exc:
                        print(
                            f"ERROR: Unable to update epic issue #{args.epic_issue}: {exc}",
                            file=sys.stderr,
                        )
                        return 2
                added_links_display = ", ".join(f"#{issue}" for issue in added_issue_links)
                print(
                    f"\nUpdated epic issue #{args.epic_issue} ## Tasks with child issue links: "
                    f"{added_links_display}"
                )
                epic_result = validate_epic_task_links(
                    epic_issue_number=args.epic_issue,
                    epic_issue_body=fixed_body,
                    owner=args.owner,
                    repo=args.repo,
                    start_issue=args.start_issue,
                    end_issue=args.end_issue,
                )
                if epic_result.is_valid:
                    print(
                        f"\nEpic issue #{args.epic_issue} contains child issue links in ## Tasks "
                        f"for #{args.start_issue}-#{args.end_issue}."
                    )
                    if not args.epic_links_only:
                        print("\nAll issues contain required sections:")
                        for issue_number in issue_numbers:
                            print(f"- #{issue_number}: OK")
                    return 0
            missing_links = ", ".join(f"#{issue}" for issue in epic_result.missing_issue_links)
            print(
                f"\nEpic issue #{args.epic_issue} is missing child issue links in ## Tasks: "
                f"{missing_links}"
            )
            return 1

        print(
            f"\nEpic issue #{args.epic_issue} contains child issue links in ## Tasks "
            f"for #{args.start_issue}-#{args.end_issue}."
        )

    if not args.epic_links_only:
        print("\nAll issues contain required sections:")
        for issue_number in issue_numbers:
            print(f"- #{issue_number}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
