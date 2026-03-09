from pathlib import Path

import pytest
from scripts.list_unresolved_review_threads import (
    extract_unresolved_review_threads,
    main,
    render_unresolved_threads_comment,
)


def test_extract_unresolved_review_threads_filters_resolved_and_invalid_nodes() -> None:
    payload = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "id": "PRRT_1",
                                "isResolved": False,
                                "url": "https://github.com/org/repo/pull/79#discussion_r100",
                            },
                            {
                                "id": "PRRT_2",
                                "isResolved": True,
                                "url": "https://github.com/org/repo/pull/79#discussion_r101",
                            },
                            {
                                "id": " ",
                                "isResolved": False,
                                "url": "https://github.com/org/repo/pull/79#discussion_r102",
                            },
                            {"id": "PRRT_3", "isResolved": False, "url": " "},
                        ]
                    }
                }
            }
        }
    }

    refs = extract_unresolved_review_threads(payload)
    assert len(refs) == 1
    assert refs[0].thread_id == "PRRT_1"
    assert refs[0].url == "https://github.com/org/repo/pull/79#discussion_r100"


def test_extract_unresolved_review_threads_accepts_nodes_root_shape() -> None:
    payload = {
        "nodes": [
            {
                "id": "PRRT_11",
                "isResolved": False,
                "url": "https://github.com/org/repo/pull/79#discussion_r111",
            },
            {
                "id": "PRRT_10",
                "isResolved": False,
                "url": "https://github.com/org/repo/pull/79#discussion_r110",
            },
        ]
    }
    refs = extract_unresolved_review_threads(payload)
    assert [ref.thread_id for ref in refs] == ["PRRT_10", "PRRT_11"]


def test_render_unresolved_threads_comment_includes_urls_and_ids() -> None:
    refs = extract_unresolved_review_threads(
        {
            "nodes": [
                {
                    "id": "PRRT_1",
                    "isResolved": False,
                    "url": "https://github.com/org/repo/pull/79#discussion_r100",
                },
                {
                    "id": "PRRT_2",
                    "isResolved": False,
                    "url": "https://github.com/org/repo/pull/79#discussion_r101",
                },
            ]
        }
    )
    comment = render_unresolved_threads_comment(pr_number=79, refs=refs)
    assert "Unresolved inline review threads for PR #79:" in comment
    assert "1. https://github.com/org/repo/pull/79#discussion_r100 (`PRRT_1`)" in comment
    assert "2. https://github.com/org/repo/pull/79#discussion_r101 (`PRRT_2`)" in comment
    assert "Total unresolved threads listed: 2" in comment


def test_render_unresolved_threads_comment_rejects_invalid_pr_number() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        render_unresolved_threads_comment(pr_number=0, refs=[])


def test_main_writes_comment_and_validates_expected_count(tmp_path: Path) -> None:
    input_json = tmp_path / "threads.json"
    output_md = tmp_path / "comment.md"
    input_json.write_text(
        """
{
  "nodes": [
    {
      "id": "PRRT_1",
      "isResolved": false,
      "url": "https://github.com/org/repo/pull/79#discussion_r100"
    },
    {
      "id": "PRRT_2",
      "isResolved": false,
      "url": "https://github.com/org/repo/pull/79#discussion_r101"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--input-json",
            str(input_json),
            "--pr-number",
            "79",
            "--output",
            str(output_md),
            "--expected-count",
            "2",
        ]
    )
    assert exit_code == 0
    generated = output_md.read_text(encoding="utf-8")
    assert "discussion_r100" in generated
    assert "discussion_r101" in generated


def test_main_raises_when_expected_count_mismatch(tmp_path: Path) -> None:
    input_json = tmp_path / "threads.json"
    output_md = tmp_path / "comment.md"
    input_json.write_text(
        """
{
  "nodes": [
    {
      "id": "PRRT_1",
      "isResolved": false,
      "url": "https://github.com/org/repo/pull/79#discussion_r100"
    }
  ]
}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Expected 2 unresolved thread\\(s\\), found 1"):
        main(
            [
                "--input-json",
                str(input_json),
                "--pr-number",
                "79",
                "--output",
                str(output_md),
                "--expected-count",
                "2",
            ]
        )
