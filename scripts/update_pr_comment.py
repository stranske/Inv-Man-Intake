#!/usr/bin/env python3
"""Post a markdown report comment to a GitHub pull request."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

DEFAULT_OWNER = "stranske"
DEFAULT_REPO = "Inv-Man-Intake"
DEFAULT_PR_NUMBER = 81
DEFAULT_REPORT = Path("data/pr81_threads_report.md")


def post_issue_comment(owner: str, repo: str, pr_number: int, token: str, body: str) -> int:
    """Post the supplied markdown body as an issue comment on the PR."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.post(url, headers=headers, json={"body": body}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "id" not in payload:
        raise ValueError("Unexpected response payload while creating PR comment")
    return int(payload["id"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--pr", type=int, default=DEFAULT_PR_NUMBER)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        help="GitHub token (defaults to GITHUB_TOKEN/GH_TOKEN).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print comment body instead of posting to GitHub.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    body = args.report.read_text(encoding="utf-8").strip()
    if not body:
        print("error: report file is empty", file=sys.stderr)
        return 2

    if args.dry_run:
        print(body)
        return 0

    if not args.token:
        print("error: missing GitHub token (set GITHUB_TOKEN or GH_TOKEN)", file=sys.stderr)
        return 2

    comment_id = post_issue_comment(args.owner, args.repo, args.pr, args.token, body)
    print(f"Posted PR comment id={comment_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
