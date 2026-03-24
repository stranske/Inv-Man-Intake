#!/usr/bin/env python3
"""List unresolved inline review threads for a pull request."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_OWNER = "stranske"
DEFAULT_REPO = "Inv-Man-Intake"
DEFAULT_PR = 83
GRAPHQL_ENDPOINT = "https://api.github.com/graphql"


@dataclass(frozen=True)
class ReviewThread:
    thread_id: str
    url: str


def _graphql_request(query: str, variables: dict[str, Any], token: str | None) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "inv-man-intake-unresolved-thread-lister",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(url=GRAPHQL_ENDPOINT, data=payload, headers=headers, method="POST")
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed GitHub API URL
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Unexpected GraphQL response payload")
    return cast(dict[str, Any], parsed)


def _extract_unresolved_threads(payload: dict[str, Any]) -> tuple[list[ReviewThread], str | None]:
    errors = payload.get("errors")
    if errors:
        raise ValueError(f"GraphQL query failed: {errors}")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("GraphQL response is missing data")

    repository = data.get("repository")
    if not isinstance(repository, dict):
        raise ValueError("GraphQL response is missing repository")

    pull_request = repository.get("pullRequest")
    if pull_request is None:
        raise ValueError("Pull request not found")
    if not isinstance(pull_request, dict):
        raise ValueError("GraphQL response has invalid pullRequest shape")

    review_threads = pull_request.get("reviewThreads")
    if not isinstance(review_threads, dict):
        raise ValueError("GraphQL response is missing reviewThreads")

    nodes = review_threads.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("GraphQL response has invalid reviewThreads.nodes")

    unresolved: list[ReviewThread] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if bool(node.get("isResolved")):
            continue

        thread_id = str(node.get("id") or "")
        comments = node.get("comments")
        url = ""
        if isinstance(comments, dict):
            comment_nodes = comments.get("nodes")
            if isinstance(comment_nodes, list) and comment_nodes:
                first_comment = comment_nodes[0]
                if isinstance(first_comment, dict):
                    url = str(first_comment.get("url") or "")

        unresolved.append(ReviewThread(thread_id=thread_id, url=url))

    page_info = review_threads.get("pageInfo")
    if not isinstance(page_info, dict):
        raise ValueError("GraphQL response is missing reviewThreads.pageInfo")

    if bool(page_info.get("hasNextPage")):
        end_cursor = page_info.get("endCursor")
        return unresolved, str(end_cursor) if end_cursor else None

    return unresolved, None


def fetch_unresolved_review_threads(
    owner: str, repo: str, pr_number: int, token: str | None
) -> list[ReviewThread]:
    query = """
    query($owner: String!, $repo: String!, $pullNumber: Int!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pullNumber) {
          reviewThreads(first: 100, after: $cursor) {
            nodes {
              id
              isResolved
              comments(first: 1) {
                nodes {
                  url
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
    """

    all_unresolved: list[ReviewThread] = []
    cursor: str | None = None

    while True:
        payload = _graphql_request(
            query=query,
            variables={
                "owner": owner,
                "repo": repo,
                "pullNumber": pr_number,
                "cursor": cursor,
            },
            token=token,
        )
        unresolved_page, cursor = _extract_unresolved_threads(payload)
        all_unresolved.extend(unresolved_page)
        if cursor is None:
            break

    return all_unresolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List unresolved inline review threads for a pull request."
    )
    parser.add_argument(
        "--owner", default=DEFAULT_OWNER, help=f"GitHub owner (default: {DEFAULT_OWNER})"
    )
    parser.add_argument(
        "--repo", default=DEFAULT_REPO, help=f"GitHub repo (default: {DEFAULT_REPO})"
    )
    parser.add_argument(
        "--pr", type=int, default=DEFAULT_PR, help=f"Pull request number (default: {DEFAULT_PR})"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub token (defaults to GITHUB_TOKEN env var if set).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        unresolved_threads = fetch_unresolved_review_threads(
            owner=args.owner,
            repo=args.repo,
            pr_number=args.pr,
            token=args.token,
        )
    except (ValueError, HTTPError, URLError) as exc:
        print(
            f"ERROR: Unable to fetch unresolved threads for PR #{args.pr}: {exc}", file=sys.stderr
        )
        return 2

    print(f"Unresolved inline review threads for PR #{args.pr}: {len(unresolved_threads)}")
    for thread in unresolved_threads:
        print(f"- {thread.thread_id} {thread.url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
