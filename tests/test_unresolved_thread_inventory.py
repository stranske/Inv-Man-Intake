"""Tests for unresolved review thread inventory extraction."""

from scripts.unresolved_thread_inventory import build_markdown, extract_unresolved_threads


def test_extract_unresolved_threads_filters_resolved_items() -> None:
    payload = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "PRRT_kwDOAAABCD1",
                                "isResolved": False,
                                "url": "https://github.com/org/repo/pull/80#discussion_r123",
                            },
                            {
                                "id": "PRRT_kwDOAAABCD2",
                                "isResolved": True,
                                "url": "https://github.com/org/repo/pull/80#discussion_r124",
                            },
                            {
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "databaseId": 2900000001,
                                            "url": "https://github.com/org/repo/pull/80#discussion_r2900000001",
                                        }
                                    ]
                                },
                            },
                        ]
                    }
                }
            }
        }
    }

    unresolved = extract_unresolved_threads(payload)

    assert unresolved == [
        {
            "identifier": "PRRT_kwDOAAABCD1",
            "url": "https://github.com/org/repo/pull/80#discussion_r123",
        },
        {
            "identifier": "discussion_r2900000001",
            "url": "https://github.com/org/repo/pull/80#discussion_r2900000001",
        },
    ]


def test_build_markdown_handles_missing_url() -> None:
    markdown = build_markdown([{"identifier": "discussion_r1", "url": ""}])

    assert "| `discussion_r1` | (missing URL in payload) |" in markdown
