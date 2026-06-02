from __future__ import annotations

from pathlib import Path

from scripts.verify_stlite_browser import (
    DEFAULT_LOG_NAME,
    DEFAULT_SCREENSHOT_NAME,
    build_artifact_paths,
    parse_args,
)


def test_artifact_paths_are_stable() -> None:
    screenshot_path, log_path = build_artifact_paths(Path("app/live-verification-artifacts"))

    assert screenshot_path == Path("app/live-verification-artifacts") / DEFAULT_SCREENSHOT_NAME
    assert log_path == Path("app/live-verification-artifacts") / DEFAULT_LOG_NAME


def test_cli_defaults_to_chrome_channel_and_expected_score() -> None:
    args = parse_args([])

    assert args.browser_channel == "chrome"
    assert args.expected_score == "0.7809"
    assert args.output_dir == Path("app/live-verification-artifacts")


def test_cli_allows_bundled_chromium_channel() -> None:
    args = parse_args(["--browser-channel", ""])

    assert args.browser_channel == ""
