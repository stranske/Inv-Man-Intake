from scripts.generate_pr_thread_review import (
    ThreadComment,
    extract_unresolved_thread_comments,
    render_review_markdown,
)


def test_extract_unresolved_thread_comments_filters_resolved_threads() -> None:
    payload = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "nodes": [
                            {
                                "isResolved": False,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/org/repo/pull/73#discussion_r1",
                                            "body": "Please add a guard clause.",
                                            "path": "src/app.py",
                                            "line": 42,
                                            "author": {"login": "reviewer-a"},
                                        }
                                    ]
                                },
                            },
                            {
                                "isResolved": True,
                                "comments": {
                                    "nodes": [
                                        {
                                            "url": "https://github.com/org/repo/pull/73#discussion_r2",
                                            "body": "This is already resolved.",
                                            "path": "src/old.py",
                                            "line": 10,
                                            "author": {"login": "reviewer-b"},
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

    result = extract_unresolved_thread_comments(payload)

    assert result == [
        ThreadComment(
            url="https://github.com/org/repo/pull/73#discussion_r1",
            body="Please add a guard clause.",
            reviewer="reviewer-a",
            path="src/app.py",
            line=42,
        )
    ]


def test_render_review_markdown_includes_required_disposition_sections() -> None:
    markdown = render_review_markdown(
        pr_number=73,
        issue_number=46,
        pr_url="https://github.com/stranske/Inv-Man-Intake/pull/73",
        comments=[
            ThreadComment(
                url="https://github.com/org/repo/pull/73#discussion_r1",
                body="Please add a guard clause to handle missing values.",
                reviewer="reviewer-a",
                path="src/app.py",
                line=42,
            )
        ],
    )

    assert "Original review comment" in markdown
    assert "Reviewer concern" in markdown
    assert "Disposition options" in markdown
    assert "Fix: implement bounded code/test change" in markdown
    assert "Defer: document rationale" in markdown
    assert "Reject: explain why the concern does not require a change" in markdown
