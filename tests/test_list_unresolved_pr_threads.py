from __future__ import annotations

from typing import Any

import pytest
from scripts import list_unresolved_pr_threads as module


def test_extract_unresolved_threads_filters_resolved() -> None:
    payload: dict[str, Any] = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "THREAD_1",
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/stranske/Inv-Man-Intake/pull/83#discussion_r1"
                                        }
                                    ]
                                },
                            },
                            {
                                "id": "THREAD_2",
                                "isResolved": True,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/stranske/Inv-Man-Intake/pull/83#discussion_r2"
                                        }
                                    ]
                                },
                            },
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
    }

    unresolved, cursor = module._extract_unresolved_threads(payload)

    assert cursor is None
    assert unresolved == [
        module.ReviewThread(
            thread_id="THREAD_1",
            url="https://github.com/stranske/Inv-Man-Intake/pull/83#discussion_r1",
        )
    ]


def test_extract_unresolved_threads_raises_on_graphql_error() -> None:
    with pytest.raises(ValueError, match="GraphQL query failed"):
        module._extract_unresolved_threads({"errors": [{"message": "Bad credentials"}]})


def test_fetch_unresolved_review_threads_handles_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "THREAD_A",
                                    "isResolved": False,
                                    "comments": {"nodes": [{"url": "https://example.test/a"}]},
                                }
                            ],
                            "pageInfo": {"hasNextPage": True, "endCursor": "CURSOR_1"},
                        }
                    }
                }
            }
        },
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "THREAD_B",
                                    "isResolved": False,
                                    "comments": {"nodes": [{"url": "https://example.test/b"}]},
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }
        },
    ]

    call_index = {"value": 0}

    def _fake_graphql_request(
        query: str, variables: dict[str, Any], token: str | None
    ) -> dict[str, Any]:
        del query, token
        index = call_index["value"]
        call_index["value"] += 1
        if index == 0:
            assert variables["cursor"] is None
        else:
            assert variables["cursor"] == "CURSOR_1"
        return responses[index]

    monkeypatch.setattr(module, "_graphql_request", _fake_graphql_request)

    unresolved = module.fetch_unresolved_review_threads(
        owner="stranske", repo="Inv-Man-Intake", pr_number=83, token="token"
    )

    assert unresolved == [
        module.ReviewThread(thread_id="THREAD_A", url="https://example.test/a"),
        module.ReviewThread(thread_id="THREAD_B", url="https://example.test/b"),
    ]


def test_main_prints_unresolved_threads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        module,
        "fetch_unresolved_review_threads",
        lambda owner, repo, pr_number, token: [
            module.ReviewThread(thread_id="THREAD_X", url="https://example.test/x"),
            module.ReviewThread(thread_id="THREAD_Y", url="https://example.test/y"),
        ],
    )

    exit_code = module.main(["--pr", "83", "--owner", "stranske", "--repo", "Inv-Man-Intake"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Unresolved inline review threads for PR #83: 2" in captured.out
    assert "- THREAD_X https://example.test/x" in captured.out
    assert "- THREAD_Y https://example.test/y" in captured.out


def test_main_returns_error_code_when_fetch_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fail(
        owner: str, repo: str, pr_number: int, token: str | None
    ) -> list[module.ReviewThread]:
        del owner, repo, pr_number, token
        raise ValueError("boom")

    monkeypatch.setattr(module, "fetch_unresolved_review_threads", _fail)

    exit_code = module.main(["--pr", "83"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "ERROR: Unable to fetch unresolved threads for PR #83" in captured.err
