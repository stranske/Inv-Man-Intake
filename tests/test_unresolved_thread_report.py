from __future__ import annotations

import json

from scripts.unresolved_thread_report import (
    extract_review_threads,
    main,
    render_unresolved_thread_report,
)

GRAPHQL_PAYLOAD = {
    "data": {
        "repository": {
            "pullRequest": {
                "reviewThreads": {
                    "nodes": [
                        {
                            "id": "PRRT_kwDOExample111",
                            "isResolved": False,
                            "comments": {
                                "nodes": [
                                    {
                                        "url": "https://github.com/org/repo/pull/72#discussion_r111",
                                        "path": "src/app.py",
                                        "line": 42,
                                        "body": "Please avoid mutating input values in-place.",
                                    }
                                ]
                            },
                        },
                        {
                            "id": "PRRT_kwDOExample222",
                            "isResolved": True,
                            "comments": {
                                "nodes": [
                                    {
                                        "url": "https://github.com/org/repo/pull/72#discussion_r222",
                                        "path": "tests/test_app.py",
                                        "line": 9,
                                        "body": "Looks good now.",
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


def test_extract_review_threads_supports_graphql_payload_shape() -> None:
    threads = extract_review_threads(GRAPHQL_PAYLOAD)
    assert len(threads) == 2
    assert threads[0].thread_url.endswith("discussion_r111")
    assert threads[0].thread_id == "PRRT_kwDOExample111"
    assert threads[0].path == "src/app.py"
    assert threads[0].line == 42
    assert threads[0].concern_excerpt == "Please avoid mutating input values in-place."
    assert threads[1].is_resolved is True


def test_render_unresolved_thread_report_includes_thread_refs_in_summary() -> None:
    threads = extract_review_threads(GRAPHQL_PAYLOAD)
    unresolved_only = [thread for thread in threads if not thread.is_resolved]
    report = render_unresolved_thread_report(
        pr_number=72,
        source_issue=36,
        tracking_issue=128,
        threads=unresolved_only,
    )

    assert "# PR #72 Unresolved Review Threads" in report
    assert "Source issue: #36" in report
    assert "Tracking issue: #128" in report
    assert "| https://github.com/org/repo/pull/72#discussion_r111 | src/app.py | 42 |" in report
    assert "`PRRT_kwDOExample111`" in report
    assert "| TODO | TODO | TODO |" in report
    assert "TODO" in report


def test_main_writes_file_and_filters_out_resolved_threads(tmp_path) -> None:
    payload_path = tmp_path / "threads.json"
    output_path = tmp_path / "report.md"
    payload_path.write_text(json.dumps(GRAPHQL_PAYLOAD), encoding="utf-8")

    exit_code = main(
        [
            "--threads-json",
            str(payload_path),
            "--pr",
            "72",
            "--source-issue",
            "36",
            "--issue",
            "128",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    report = output_path.read_text(encoding="utf-8")
    assert "discussion_r111" in report
    assert "discussion_r222" not in report


def test_render_summary_falls_back_to_discussion_ref_without_thread_id() -> None:
    payload = {
        "threads": [
            {
                "isResolved": False,
                "comments": {
                    "nodes": [
                        {
                            "url": "https://github.com/org/repo/pull/72#discussion_r999",
                            "path": "src/mod.py",
                            "line": 11,
                            "body": "Example comment",
                        }
                    ]
                },
            }
        ]
    }
    threads = extract_review_threads(payload)
    report = render_unresolved_thread_report(
        pr_number=72,
        source_issue=36,
        tracking_issue=128,
        threads=threads,
    )
    assert "`discussion_r999`" in report
