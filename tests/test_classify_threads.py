from __future__ import annotations

from scripts.classify_threads import classify_thread


def test_classify_thread_returns_expected_keys() -> None:
    result = classify_thread({"comments": [{"body": "nit: consider renaming this variable"}]})
    assert set(result.keys()) == {"classification", "rationale"}
    assert result["classification"] in {"warranted", "not-warranted"}
    assert result["rationale"].strip() != ""


def test_classify_thread_style_comment_is_not_warranted() -> None:
    thread = {"comments": [{"body": "Style nit: this wording is hard to read."}]}
    result = classify_thread(thread)
    assert result["classification"] == "not-warranted"


def test_classify_thread_bug_comment_is_warranted() -> None:
    thread = {"comments": [{"body": "This is incorrect and causes a regression for null values."}]}
    result = classify_thread(thread)
    assert result["classification"] == "warranted"


def test_classify_thread_empty_text_defaults_to_warranted() -> None:
    result = classify_thread({"comments": []})
    assert result["classification"] == "warranted"
    assert "defaulting to warranted" in result["rationale"].lower()
