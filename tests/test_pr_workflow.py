from __future__ import annotations

from typing import Any

from scripts.classify_threads import classify_threads_document
from scripts.fetch_pr_threads import build_output_document, fetch_unresolved_threads
from scripts.generate_classification_report import generate_markdown_table
from scripts.update_pr_comment import post_issue_comment
from scripts.validate_classification_output import find_invalid_threads


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


def test_pr_thread_workflow_end_to_end_with_mocked_github_api(monkeypatch) -> None:
    posted_comments: list[dict[str, Any]] = []

    def fake_post(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url.endswith("/graphql"):
            return _FakeResponse(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                    "nodes": [
                                        {
                                            "id": "PRRT_1",
                                            "isResolved": False,
                                            "isOutdated": False,
                                            "path": "src/inv_man_intake/scoring/engine.py",
                                            "line": 10,
                                            "startLine": 9,
                                            "originalLine": 10,
                                            "originalStartLine": 9,
                                            "comments": {
                                                "nodes": [
                                                    {
                                                        "id": "PRRC_1",
                                                        "databaseId": 123,
                                                        "author": {"login": "reviewer"},
                                                        "body": "This is incorrect and causes a bug.",
                                                        "createdAt": "2026-03-09T00:00:00Z",
                                                        "url": "https://example.test/comment/1",
                                                    }
                                                ]
                                            },
                                        }
                                    ],
                                }
                            }
                        }
                    }
                }
            )

        posted_comments.append(kwargs.get("json", {}))
        return _FakeResponse({"id": 999})

    monkeypatch.setattr("scripts.fetch_pr_threads.requests.post", fake_post)
    monkeypatch.setattr("scripts.update_pr_comment.requests.post", fake_post)

    threads = fetch_unresolved_threads("stranske", "Inv-Man-Intake", 81, "token")
    assert len(threads) == 1

    document = build_output_document("stranske", "Inv-Man-Intake", 81, threads)
    classified = classify_threads_document(document)
    invalid = find_invalid_threads(classified)
    assert invalid == []

    report = generate_markdown_table(classified)
    assert "| Thread ID | Classification | Rationale |" in report
    assert "| PRRT_1 | warranted |" in report

    comment_id = post_issue_comment("stranske", "Inv-Man-Intake", 81, "token", report)
    assert comment_id == 999
    assert len(posted_comments) == 1
    assert posted_comments[0]["body"] == report
