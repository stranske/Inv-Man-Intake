from __future__ import annotations

import json
from pathlib import Path

from scripts.list_unresolved_review_threads import main, parse_unresolved_threads


def _payload() -> dict:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "isResolved": True,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": (
                                                "https://github.com/stranske/Inv-Man-Intake/pull/74"
                                                "#discussion_r111"
                                            ),
                                            "body": "already resolved",
                                            "path": "src/foo.py",
                                            "line": 10,
                                            "author": {"login": "reviewer-a"},
                                        }
                                    ]
                                },
                            },
                            {
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": (
                                                "https://github.com/stranske/Inv-Man-Intake/pull/74"
                                                "#discussion_r222"
                                            ),
                                            "body": "Please add guard clause.",
                                            "path": "src/app.py",
                                            "line": 42,
                                            "author": {"login": "reviewer-b"},
                                        }
                                    ]
                                },
                            },
                            {
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": (
                                                "https://github.com/stranske/Inv-Man-Intake/pull/74"
                                                "#discussion_r333"
                                            ),
                                            "body": "Prefer explicit error handling.",
                                            "path": "src/service.py",
                                            "line": None,
                                            "originalLine": 88,
                                            "author": None,
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


def test_parse_unresolved_threads_filters_resolved_and_extracts_fields() -> None:
    results = parse_unresolved_threads(_payload())
    assert len(results) == 2

    first = results[0]
    assert first.thread_url == "https://github.com/stranske/Inv-Man-Intake/pull/74"
    assert first.comment_url == "https://github.com/stranske/Inv-Man-Intake/pull/74#discussion_r222"
    assert first.author == "reviewer-b"
    assert first.comment_text == "Please add guard clause."
    assert first.path == "src/app.py"
    assert first.line == 42

    second = results[1]
    assert second.author == "unknown"
    assert second.line == 88


def test_main_markdown_with_input_json(tmp_path: Path, capsys) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(_payload()), encoding="utf-8")

    exit_code = main(["--pr", "74", "--input-json", str(payload_path), "--format", "markdown"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "# PR #74 Unresolved Inline Review Threads" in captured.out
    assert "discussion_r222" in captured.out
    assert "discussion_r333" in captured.out
    assert "discussion_r111" not in captured.out


def test_main_json_output_with_input_json(tmp_path: Path, capsys) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(_payload()), encoding="utf-8")

    exit_code = main(["--pr", "74", "--input-json", str(payload_path), "--format", "json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    data = json.loads(captured.out)
    assert [item["comment_url"] for item in data] == [
        "https://github.com/stranske/Inv-Man-Intake/pull/74#discussion_r222",
        "https://github.com/stranske/Inv-Man-Intake/pull/74#discussion_r333",
    ]
