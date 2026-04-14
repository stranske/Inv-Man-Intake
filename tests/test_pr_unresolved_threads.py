from pathlib import Path

from scripts import pr_unresolved_threads
from scripts.pr_unresolved_threads import (
    ReviewComment,
    ReviewThread,
    main,
    render_disposition_plan_comment,
    render_issue_comment,
)


def test_fetch_review_threads_handles_pagination(monkeypatch) -> None:
    responses = [
        {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "nodes": [
                                {
                                    "id": "T1",
                                    "isResolved": False,
                                    "path": "src/a.py",
                                    "line": 10,
                                    "comments": {
                                        "nodes": [{"url": "https://example.test/thread-1"}]
                                    },
                                }
                            ],
                            "pageInfo": {"hasNextPage": True, "endCursor": "abc"},
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
                                    "id": "T2",
                                    "isResolved": True,
                                    "path": "src/b.py",
                                    "line": 20,
                                    "comments": {
                                        "nodes": [{"url": "https://example.test/thread-2"}]
                                    },
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }
        },
    ]
    cursor_values: list[str | None] = []

    def _fake_run_graphql(*, query: str, variables: dict[str, object]) -> dict[str, object]:
        del query
        cursor_values.append(variables.get("cursor"))  # type: ignore[arg-type]
        return responses.pop(0)

    monkeypatch.setattr(pr_unresolved_threads, "_run_graphql", _fake_run_graphql)
    threads = pr_unresolved_threads.fetch_review_threads("stranske/Inv-Man-Intake", 78)
    assert [thread.thread_id for thread in threads] == ["T1", "T2"]
    assert cursor_values == [None, "abc"]


def test_render_issue_comment_lists_urls() -> None:
    threads = [
        ReviewThread(
            thread_id="T1",
            is_resolved=False,
            path="src/a.py",
            line=10,
            url="https://github.com/org/repo/pull/78#discussion_r1",
        ),
        ReviewThread(
            thread_id="T2",
            is_resolved=False,
            path="src/b.py",
            line=20,
            url="https://github.com/org/repo/pull/78#discussion_r2",
        ),
    ]
    comment = render_issue_comment(78, threads)
    assert "PR #78 (2 total)" in comment
    assert "1. https://github.com/org/repo/pull/78#discussion_r1" in comment
    assert "2. https://github.com/org/repo/pull/78#discussion_r2" in comment


def test_render_disposition_plan_comment_includes_reviewer_context() -> None:
    threads = [
        ReviewThread(
            thread_id="T1",
            is_resolved=False,
            path="src/a.py",
            line=10,
            url="https://github.com/org/repo/pull/78#discussion_r1",
            comments=(
                ReviewComment(
                    url="https://github.com/org/repo/pull/78#discussion_r1",
                    author="reviewer1",
                    body="Please clarify this condition and add a regression test for null input.",
                    created_at="2026-03-01T01:00:00Z",
                ),
            ),
        )
    ]
    comment = render_disposition_plan_comment(78, threads)
    assert "Proposed disposition plan for unresolved review threads on PR #78:" in comment
    assert "Reviewer concern (reviewer1): Please clarify this condition" in comment
    assert "Proposed disposition: Likely requires follow-up code fix." in comment
    assert "Reasoning: Reviewer concern mentions potential functional risk" in comment


def test_render_disposition_plan_comment_classifies_editorial_feedback() -> None:
    threads = [
        ReviewThread(
            thread_id="T1",
            is_resolved=False,
            path="src/a.py",
            line=10,
            url="https://github.com/org/repo/pull/78#discussion_r1",
            comments=(
                ReviewComment(
                    url="https://github.com/org/repo/pull/78#discussion_r1",
                    author="reviewer1",
                    body="Nit: this wording is unclear; please clarify docs and naming.",
                    created_at="2026-03-01T01:00:00Z",
                ),
            ),
        )
    ]
    comment = render_disposition_plan_comment(78, threads)
    assert "Proposed disposition: Likely no code change needed" in comment
    assert "Reasoning: Reviewer concern appears editorial or clarity-oriented" in comment


def test_render_disposition_plan_comment_handles_empty_threads() -> None:
    comment = render_disposition_plan_comment(78, [])
    assert "No unresolved inline review threads found" in comment


def test_main_writes_outputs_and_validates_expected_count(tmp_path: Path, monkeypatch) -> None:
    json_path = tmp_path / "threads.json"
    comment_path = tmp_path / "issue-comment.md"
    disposition_comment_path = tmp_path / "disposition-comment.md"

    monkeypatch.setattr(
        pr_unresolved_threads,
        "fetch_review_threads",
        lambda repo, pr_number: [
            ReviewThread(
                thread_id="T1",
                is_resolved=False,
                path="src/a.py",
                line=10,
                url="https://github.com/org/repo/pull/78#discussion_r1",
            ),
            ReviewThread(
                thread_id="T2",
                is_resolved=False,
                path="src/b.py",
                line=20,
                url="https://github.com/org/repo/pull/78#discussion_r2",
            ),
        ],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_unresolved_threads.py",
            "--repo",
            "stranske/Inv-Man-Intake",
            "--pr-number",
            "78",
            "--expected-count",
            "2",
            "--json-output",
            str(json_path),
            "--issue-comment-output",
            str(comment_path),
            "--disposition-comment-output",
            str(disposition_comment_path),
        ],
    )
    assert main() == 0
    assert '"thread_id": "T1"' in json_path.read_text(encoding="utf-8")
    assert "Unresolved inline review threads for PR #78 (2 total):" in comment_path.read_text(
        encoding="utf-8"
    )
    assert "Proposed disposition plan for unresolved review threads on PR #78:" in (
        disposition_comment_path.read_text(encoding="utf-8")
    )


def test_main_fails_on_expected_count_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(
        pr_unresolved_threads,
        "fetch_review_threads",
        lambda repo, pr_number: [
            ReviewThread(
                thread_id="T1",
                is_resolved=False,
                path="src/a.py",
                line=10,
                url="https://github.com/org/repo/pull/78#discussion_r1",
            )
        ],
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_unresolved_threads.py",
            "--repo",
            "stranske/Inv-Man-Intake",
            "--pr-number",
            "78",
            "--expected-count",
            "2",
        ],
    )
    assert main() == 2


def test_main_returns_error_code_on_fetch_failure(monkeypatch) -> None:
    def _fail_fetch(repo: str, pr_number: int) -> list[ReviewThread]:
        del repo, pr_number
        raise RuntimeError("error connecting to api.github.com")

    monkeypatch.setattr(pr_unresolved_threads, "fetch_review_threads", _fail_fetch)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_unresolved_threads.py",
            "--repo",
            "stranske/Inv-Man-Intake",
            "--pr-number",
            "78",
        ],
    )
    assert main() == 1


def test_main_posts_issue_comment(monkeypatch) -> None:
    monkeypatch.setattr(
        pr_unresolved_threads,
        "fetch_review_threads",
        lambda repo, pr_number: [
            ReviewThread(
                thread_id="T1",
                is_resolved=False,
                path="src/a.py",
                line=10,
                url="https://github.com/org/repo/pull/78#discussion_r1",
            )
        ],
    )
    posted: dict[str, object] = {}

    def _fake_post_issue_comment(*, repo: str, issue_number: int, body: str) -> None:
        posted["repo"] = repo
        posted["issue_number"] = issue_number
        posted["body"] = body

    monkeypatch.setattr(pr_unresolved_threads, "_post_issue_comment", _fake_post_issue_comment)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_unresolved_threads.py",
            "--repo",
            "stranske/Inv-Man-Intake",
            "--pr-number",
            "78",
            "--issue-number",
            "41",
            "--post-issue-comment",
        ],
    )
    assert main() == 0
    assert posted["repo"] == "stranske/Inv-Man-Intake"
    assert posted["issue_number"] == 41
    assert "Unresolved inline review threads for PR #78 (1 total):" in str(posted["body"])


def test_main_fails_when_post_issue_comment_missing_issue_number(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_unresolved_threads.py",
            "--repo",
            "stranske/Inv-Man-Intake",
            "--pr-number",
            "78",
            "--post-issue-comment",
        ],
    )
    assert main() == 1


def test_main_fails_when_post_disposition_comment_missing_issue_number(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_unresolved_threads.py",
            "--repo",
            "stranske/Inv-Man-Intake",
            "--pr-number",
            "78",
            "--post-disposition-comment",
        ],
    )
    assert main() == 1


def test_main_returns_error_when_issue_comment_post_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        pr_unresolved_threads,
        "fetch_review_threads",
        lambda repo, pr_number: [
            ReviewThread(
                thread_id="T1",
                is_resolved=False,
                path="src/a.py",
                line=10,
                url="https://github.com/org/repo/pull/78#discussion_r1",
            )
        ],
    )

    def _fail_post_issue_comment(*, repo: str, issue_number: int, body: str) -> None:
        del repo, issue_number, body
        raise RuntimeError("cannot post issue comment")

    monkeypatch.setattr(pr_unresolved_threads, "_post_issue_comment", _fail_post_issue_comment)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_unresolved_threads.py",
            "--repo",
            "stranske/Inv-Man-Intake",
            "--pr-number",
            "78",
            "--issue-number",
            "41",
            "--post-issue-comment",
        ],
    )
    assert main() == 1


def test_main_posts_disposition_comment(monkeypatch) -> None:
    monkeypatch.setattr(
        pr_unresolved_threads,
        "fetch_review_threads",
        lambda repo, pr_number: [
            ReviewThread(
                thread_id="T1",
                is_resolved=False,
                path="src/a.py",
                line=10,
                url="https://github.com/org/repo/pull/78#discussion_r1",
                comments=(
                    ReviewComment(
                        url="https://github.com/org/repo/pull/78#discussion_r1",
                        author="reviewer1",
                        body="Need a fix here.",
                        created_at="2026-03-01T01:00:00Z",
                    ),
                ),
            )
        ],
    )
    posted: dict[str, object] = {}

    def _fake_post_issue_comment(*, repo: str, issue_number: int, body: str) -> None:
        posted["repo"] = repo
        posted["issue_number"] = issue_number
        posted["body"] = body

    monkeypatch.setattr(pr_unresolved_threads, "_post_issue_comment", _fake_post_issue_comment)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pr_unresolved_threads.py",
            "--repo",
            "stranske/Inv-Man-Intake",
            "--pr-number",
            "78",
            "--issue-number",
            "41",
            "--post-disposition-comment",
        ],
    )
    assert main() == 0
    assert posted["repo"] == "stranske/Inv-Man-Intake"
    assert posted["issue_number"] == 41
    assert "Proposed disposition plan for unresolved review threads on PR #78:" in str(
        posted["body"]
    )
