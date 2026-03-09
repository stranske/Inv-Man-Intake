from __future__ import annotations

import pytest

from scripts.thread_reply_builder import (
    ThreadDisposition,
    build_thread_reply,
    main,
    parse_thread_inventory,
    render_replies_markdown,
)

SAMPLE_INVENTORY = """
# PR #70 Unresolved Review Threads

| Thread URL | Classification | Rationale | Disposition |
| --- | --- | --- | --- |
| https://github.com/stranske/Inv-Man-Intake/pull/70#discussion_r1001 | warranted-fix | Concern is valid. | Addressed in follow-up PR #150 with commit `abcdef1`. |
| https://github.com/stranske/Inv-Man-Intake/pull/70#discussion_r1002 | not-warranted | Existing implementation already satisfies behavior. | No additional code changes required. |
"""


def test_parse_thread_inventory_extracts_discussions_and_sentences() -> None:
    items = parse_thread_inventory(SAMPLE_INVENTORY)
    assert [item.discussion_id for item in items] == ["discussion_r1001", "discussion_r1002"]
    assert items[0].classification == "warranted-fix"
    assert items[1].rationale.endswith(".")


def test_build_thread_reply_for_not_warranted_is_complete_sentence() -> None:
    item = ThreadDisposition(
        thread_url="https://github.com/stranske/Inv-Man-Intake/pull/70#discussion_r1002",
        discussion_id="discussion_r1002",
        classification="not-warranted",
        rationale="Existing implementation already satisfies behavior.",
        disposition="No additional code changes required.",
    )

    reply = build_thread_reply(item)
    assert reply == (
        "This change is not warranted because existing implementation already satisfies behavior."
    )


def test_build_thread_reply_for_warranted_fix_requires_reference() -> None:
    item = ThreadDisposition(
        thread_url="https://github.com/stranske/Inv-Man-Intake/pull/70#discussion_r1001",
        discussion_id="discussion_r1001",
        classification="warranted-fix",
        rationale="Concern is valid.",
        disposition="Implemented a fix.",
    )

    with pytest.raises(ValueError, match="must include a PR/commit reference"):
        build_thread_reply(item)


def test_render_replies_markdown_lists_per_thread_reply() -> None:
    items = parse_thread_inventory(SAMPLE_INVENTORY)
    markdown = render_replies_markdown(items)

    assert "## Thread Reply Drafts" in markdown
    assert "`discussion_r1001`" in markdown
    assert "Addressed in follow-up PR #150" in markdown
    assert "This change is not warranted because" in markdown


def test_main_writes_output_file(tmp_path) -> None:
    inventory_path = tmp_path / "inventory.md"
    output_path = tmp_path / "replies.md"
    inventory_path.write_text(SAMPLE_INVENTORY, encoding="utf-8")

    assert main(["--inventory", str(inventory_path), "--output", str(output_path)]) == 0
    generated = output_path.read_text(encoding="utf-8")
    assert "discussion_r1001" in generated
    assert "discussion_r1002" in generated
