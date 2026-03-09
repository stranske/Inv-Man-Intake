#!/usr/bin/env python3
"""Fetch unresolved review threads for a pull request via GitHub GraphQL API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_json_module = json

try:
    import requests  # type: ignore[import-untyped]
except ModuleNotFoundError:
    class _SimpleResponse:
        def __init__(self, payload: Any, status_code: int) -> None:
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self) -> Any:
            return self._payload

    class _RequestsFallback:
        @staticmethod
        def post(
            url: str,
            *,
            headers: dict[str, str] | None = None,
            json: dict[str, Any] | None = None,  # noqa: A002 - requests API compatibility
            timeout: int = 30,
        ) -> _SimpleResponse:
            data = None
            req_headers = dict(headers or {})
            if json is not None:
                data = _json_module.dumps(json).encode("utf-8")
                req_headers.setdefault("Content-Type", "application/json")
            request = Request(url=url, data=data, headers=req_headers, method="POST")
            try:
                with urlopen(request, timeout=timeout) as response:
                    raw = response.read().decode("utf-8")
                    payload = _json_module.loads(raw) if raw else {}
                    return _SimpleResponse(payload, int(response.status))
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
            except URLError as exc:
                raise RuntimeError(f"Request failed: {exc.reason}") from exc

    requests = _RequestsFallback()  # type: ignore[assignment]

DEFAULT_OWNER = "stranske"
DEFAULT_REPO = "Inv-Man-Intake"
DEFAULT_PR_NUMBER = 81
DEFAULT_OUTPUT = Path("data/pr81_threads.json")
GRAPHQL_URL = "https://api.github.com/graphql"


def _graphql_query() -> str:
    return """
query($owner: String!, $repo: String!, $pr: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          startLine
          originalLine
          originalStartLine
          comments(first: 100) {
            nodes {
              id
              databaseId
              author { login }
              body
              createdAt
              url
            }
          }
        }
      }
    }
  }
}
""".strip()


def _post_graphql(*, token: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.post(
        GRAPHQL_URL,
        headers=headers,
        json={"query": _graphql_query(), "variables": variables},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Unexpected GraphQL response payload type")
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL returned errors: {payload['errors']}")
    return payload


def fetch_unresolved_threads(
    owner: str, repo: str, pr_number: int, token: str
) -> list[dict[str, Any]]:
    """Return unresolved review thread records for a PR."""
    unresolved: list[dict[str, Any]] = []
    after: str | None = None

    while True:
        payload = _post_graphql(
            token=token,
            variables={"owner": owner, "repo": repo, "pr": pr_number, "after": after},
        )
        repository = payload.get("data", {}).get("repository")
        if repository is None:
            raise ValueError("GraphQL response is missing repository data")

        pull_request = repository.get("pullRequest")
        if pull_request is None:
            raise ValueError(f"Pull request #{pr_number} was not found")

        thread_connection = pull_request.get("reviewThreads") or {}
        nodes = thread_connection.get("nodes") or []
        for node in nodes:
            if node.get("isResolved"):
                continue
            comments = node.get("comments", {}).get("nodes") or []
            unresolved.append(
                {
                    "thread_id": node.get("id"),
                    "is_outdated": bool(node.get("isOutdated")),
                    "path": node.get("path"),
                    "line": node.get("line"),
                    "start_line": node.get("startLine"),
                    "original_line": node.get("originalLine"),
                    "original_start_line": node.get("originalStartLine"),
                    "comments": comments,
                }
            )

        page_info = thread_connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")

    return unresolved


def build_output_document(
    owner: str, repo: str, pr_number: int, threads: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return serializable output document."""
    return {
        "owner": owner,
        "repo": repo,
        "pr_number": pr_number,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "unresolved_thread_count": len(threads),
        "threads": threads,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--pr", type=int, default=DEFAULT_PR_NUMBER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        help="GitHub token (defaults to GITHUB_TOKEN/GH_TOKEN).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.token:
        print("error: missing GitHub token (set GITHUB_TOKEN or GH_TOKEN)", file=sys.stderr)
        return 2

    threads = fetch_unresolved_threads(args.owner, args.repo, args.pr, args.token)
    output = build_output_document(args.owner, args.repo, args.pr, threads)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    print(
        f"Wrote {output['unresolved_thread_count']} unresolved thread(s) to {args.output}",
        file=sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
