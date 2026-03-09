from __future__ import annotations

import json
from pathlib import Path

from scripts.langchain.unresolved_thread_inventory import (
    extract_unresolved_threads,
    main,
    render_unresolved_threads_comment,
)


def _sample_payload() -> dict:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "PRRT_1",
                                "isResolved": False,
                                "path": "src/example.py",
                                "line": 42,
                                "startLine": None,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/org/repo/pull/71#discussion_r1",
                                            "body": "Please guard this branch against missing keys.",
                                        }
                                    ]
                                },
                            },
                            {
                                "id": "PRRT_2",
                                "isResolved": False,
                                "path": "tests/test_example.py",
                                "line": None,
                                "startLine": 17,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/org/repo/pull/71#discussion_r2",
                                            "body": "Add a regression test for the edge case.",
                                        }
                                    ]
                                },
                            },
                            {
                                "id": "PRRT_3",
                                "isResolved": True,
                                "path": "ignored.py",
                                "line": 1,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/org/repo/pull/71#discussion_r3",
                                            "body": "Already resolved.",
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


def test_extract_unresolved_threads_filters_resolved_threads() -> None:
    threads = extract_unresolved_threads(_sample_payload())
    assert len(threads) == 2
    assert threads[0].path == "src/example.py"
    assert threads[0].line == 42
    assert threads[1].path == "tests/test_example.py"
    assert threads[1].line == 17


def test_extract_unresolved_threads_normalizes_summary() -> None:
    payload = _sample_payload()
    payload["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]["comments"]["nodes"][
        0
    ]["body"] = "  Needs\n\nmore   deterministic   sorting.  "
    threads = extract_unresolved_threads(payload)
    assert threads[0].summary == "Needs more deterministic sorting."


def test_render_unresolved_threads_comment_includes_required_fields() -> None:
    threads = extract_unresolved_threads(_sample_payload())
    rendered = render_unresolved_threads_comment(pr_number=71, threads=threads)
    assert "Unresolved inline review thread inventory for PR #71:" in rendered
    assert "| Thread | File | Line | Concern summary |" in rendered
    assert "https://github.com/org/repo/pull/71#discussion_r1" in rendered
    assert "`src/example.py`" in rendered
    assert "| 42 |" in rendered
    assert "Please guard this branch against missing keys." in rendered
    assert "Total unresolved threads captured: 2" in rendered


def test_main_writes_output_and_enforces_expected_count(tmp_path: Path, capsys) -> None:
    payload_path = tmp_path / "payload.json"
    out_path = tmp_path / "inventory.md"
    payload_path.write_text(json.dumps(_sample_payload()), encoding="utf-8")

    assert (
        main(
            [
                "--input-file",
                str(payload_path),
                "--pr",
                "71",
                "--output",
                str(out_path),
                "--expected-count",
                "2",
            ]
        )
        == 0
    )
    written = out_path.read_text(encoding="utf-8")
    assert "PR #71" in written

    assert (
        main(
            [
                "--input-file",
                str(payload_path),
                "--pr",
                "71",
                "--expected-count",
                "4",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert "expected 4 unresolved threads, found 2" in captured.out
