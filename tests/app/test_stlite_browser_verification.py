from __future__ import annotations

from pathlib import Path

from scripts.verify_static_spa_pyodide import (
    DEFAULT_LOG_NAME,
    DEFAULT_SCREENSHOT_NAME,
    build_artifact_paths,
    is_local_browser_url,
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


def test_cli_accepts_offline_mode() -> None:
    args = parse_args(["--offline"])

    assert args.offline is True


def test_offline_url_filter_allows_only_local_browser_urls() -> None:
    assert is_local_browser_url("http://127.0.0.1:8000/app/index.html")
    assert is_local_browser_url("http://localhost:8000/app/index.html")
    assert is_local_browser_url("blob:http://127.0.0.1:8000/token")
    assert is_local_browser_url("data:text/plain,ok")
    assert is_local_browser_url("about:blank")
    assert not is_local_browser_url("https://cdn.jsdelivr.net/npm/pyodide")
