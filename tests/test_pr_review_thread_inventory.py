import json
from pathlib import Path

from scripts.pr_review_thread_inventory import (
    extract_unresolved_threads,
    main,
    render_pr_comment,
)


def _payload() -> dict:
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "PRRT_kwDOExampleA",
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "databaseId": 2901889997,
                                            "url": (
                                                "https://github.com/stranske/Inv-Man-Intake/pull/75"
                                                "#discussion_r2901889997"
                                            ),
                                        }
                                    ]
                                },
                            },
                            {
                                "id": "PRRT_kwDOExampleB",
                                "isResolved": True,
                                "comments": {
                                    "nodes": [
                                        {
                                            "databaseId": 2901889994,
                                            "url": (
                                                "https://github.com/stranske/Inv-Man-Intake/pull/75"
                                                "#discussion_r2901889994"
                                            ),
                                        }
                                    ]
                                },
                            },
                            {
                                "id": "PRRT_kwDOExampleC",
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "databaseId": 2901889973,
                                            "url": (
                                                "https://github.com/stranske/Inv-Man-Intake/pull/75"
                                                "#discussion_r2901889973"
                                            ),
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


def test_extract_unresolved_threads_filters_resolved_and_sorts() -> None:
    threads = extract_unresolved_threads(_payload(), pr_number=75)
    assert [thread.identifier for thread in threads] == [
        "discussion_r2901889973",
        "discussion_r2901889997",
    ]
    assert threads[0].url.endswith("#discussion_r2901889973")
    assert threads[1].url.endswith("#discussion_r2901889997")


def test_render_pr_comment_includes_identifiers_and_links() -> None:
    comment = render_pr_comment(
        pr_number=75,
        threads=extract_unresolved_threads(_payload(), pr_number=75),
    )
    assert "Unresolved review thread inventory for PR #75" in comment
    assert "Identified 2 unresolved inline review thread(s):" in comment
    assert (
        "`discussion_r2901889973` - https://github.com/stranske/Inv-Man-Intake/pull/75" in comment
    )


def test_main_writes_comment_file_when_count_matches(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "review-threads.json"
    output_path = tmp_path / "comment.md"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_review_thread_inventory.py",
            "--input",
            str(input_path),
            "--pr-number",
            "75",
            "--output",
            str(output_path),
            "--expected-count",
            "2",
        ],
    )

    assert main() == 0
    content = output_path.read_text(encoding="utf-8")
    assert "Identified 2 unresolved inline review thread(s):" in content


def test_main_fails_when_expected_count_mismatch(tmp_path: Path, monkeypatch, capsys) -> None:
    input_path = tmp_path / "review-threads.json"
    output_path = tmp_path / "comment.md"
    input_path.write_text(json.dumps(_payload()), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_review_thread_inventory.py",
            "--input",
            str(input_path),
            "--pr-number",
            "75",
            "--output",
            str(output_path),
            "--expected-count",
            "5",
        ],
    )

    assert main() == 1
    assert not output_path.exists()
    captured = capsys.readouterr()
    assert "expected 5, found 2" in captured.err
