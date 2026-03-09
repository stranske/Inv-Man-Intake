from __future__ import annotations

import json
from pathlib import Path

from scripts.pr_review_thread_inventory import load_payload, parse_review_threads, render_markdown


def _payload() -> dict[str, object]:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "isResolved": False,
                                "path": "src/inv_man_intake/images/extractor.py",
                                "line": 120,
                                "originalLine": 118,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r1",
                                            "body": "Please add a guard for empty OCR chunks to avoid a noisy fallback.",
                                        }
                                    ]
                                },
                            },
                            {
                                "isResolved": True,
                                "path": "tests/images/test_extractor.py",
                                "line": 44,
                                "originalLine": 44,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/stranske/Inv-Man-Intake/pull/85#discussion_r2",
                                            "body": "This was resolved already.",
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


def test_parse_review_threads_filters_resolved_by_default() -> None:
    records = parse_review_threads(_payload())
    assert len(records) == 1
    assert records[0].thread_url.endswith("discussion_r1")
    assert records[0].path == "src/inv_man_intake/images/extractor.py"
    assert records[0].line == 120
    assert not records[0].is_resolved


def test_parse_review_threads_can_include_resolved() -> None:
    records = parse_review_threads(_payload(), unresolved_only=False)
    assert len(records) == 2
    assert records[1].is_resolved


def test_render_markdown_contains_expected_columns() -> None:
    markdown = render_markdown(parse_review_threads(_payload(), unresolved_only=False))
    assert "| Thread URL | File | Line | Status | Summary |" in markdown
    assert "discussion_r1" in markdown
    assert "discussion_r2" in markdown
    assert "unresolved" in markdown
    assert "resolved" in markdown


def test_load_payload_reads_local_json(tmp_path: Path) -> None:
    payload = _payload()
    payload_path = tmp_path / "threads.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_payload(payload_path, owner="stranske", repo="Inv-Man-Intake", pr_number=85)
    assert loaded == payload
