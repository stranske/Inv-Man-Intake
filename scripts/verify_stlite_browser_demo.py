"""Capture real headless-browser evidence for the stlite intake demo."""

from __future__ import annotations

import argparse
import contextlib
import http.server
import json
import socketserver
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_SCORE = "0.7809"
DEFAULT_FIXTURE = "pdf_primary_mixed_bundle.json"


@dataclass(frozen=True)
class BrowserEvidence:
    url: str
    fixture_name: str
    expected_score: str
    observed_score: str
    screenshot_path: str
    browser_log_path: str
    selector_checks: dict[str, bool]


class _StaticServer(socketserver.TCPServer):
    allow_reuse_address = True


@contextlib.contextmanager
def _serve_repo(repo_root: Path) -> Any:
    handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(  # noqa: E731
        *args,
        directory=str(repo_root),
        **kwargs,
    )
    with _StaticServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{httpd.server_address[1]}"
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _normalize_artifact_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def write_evidence(evidence: BrowserEvidence, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(evidence), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_browser_verification(
    *,
    repo_root: Path,
    fixture_name: str,
    expected_score: str,
    screenshot_path: Path,
    log_path: Path,
    executable_path: str | None = None,
    timeout_ms: int = 120_000,
) -> BrowserEvidence:
    """Run the stlite app in a real browser and capture screenshot + selector evidence."""

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised by CLI users without extra deps.
        raise SystemExit(
            "Playwright is required for browser verification. Install with "
            '`python -m pip install -e ".[app,browser]"` and then run '
            "`python -m playwright install chromium` if no Chrome executable is available."
        ) from exc

    repo_root = repo_root.resolve()
    screenshot_path = screenshot_path.resolve()
    log_path = log_path.resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    console_lines: list[str] = []
    with _serve_repo(repo_root) as base_url, sync_playwright() as p:
        url = f"{base_url}/app/index.html"
        launch_args: dict[str, object] = {
            "headless": True,
            "args": ["--no-first-run", "--no-default-browser-check"],
        }
        if executable_path:
            launch_args["executable_path"] = executable_path
        browser = p.chromium.launch(**launch_args)
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1100},
                record_har_path=str(log_path.with_suffix(".har")),
            )
            page = context.new_page()
            page.on("console", lambda msg: console_lines.append(f"{msg.type}: {msg.text}"))
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            page.get_by_text("Inv-Man-Intake").wait_for(timeout=timeout_ms)
            page.get_by_text(fixture_name).wait_for(timeout=timeout_ms)
            page.get_by_text(expected_score).wait_for(timeout=timeout_ms)
            page.get_by_text("Explainability").wait_for(timeout=timeout_ms)
            page.get_by_text("Analyst queue").wait_for(timeout=timeout_ms)
            page.screenshot(path=str(screenshot_path), full_page=True)
            context.close()
        except (PlaywrightError, PlaywrightTimeoutError):
            log_path.write_text("\n".join(console_lines), encoding="utf-8")
            raise
        finally:
            browser.close()

    selector_checks = {
        "title": True,
        "fixture": True,
        "score": True,
        "explainability": True,
        "analyst_queue": True,
    }
    evidence = BrowserEvidence(
        url=url,
        fixture_name=fixture_name,
        expected_score=expected_score,
        observed_score=expected_score,
        screenshot_path=_normalize_artifact_path(screenshot_path, repo_root),
        browser_log_path=_normalize_artifact_path(log_path, repo_root),
        selector_checks=selector_checks,
    )
    log_path.write_text(
        "\n".join(
            [
                f"url={evidence.url}",
                f"fixture={fixture_name}",
                f"observed_score={expected_score}",
                "selector_checks=" + json.dumps(selector_checks, sort_keys=True),
                "console:",
                *console_lines,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--expected-score", default=DEFAULT_SCORE)
    parser.add_argument(
        "--screenshot",
        type=Path,
        default=Path("app/live-verification-browser.png"),
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("app/live-verification-browser.log"),
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("app/live-verification-browser.json"),
    )
    parser.add_argument(
        "--chrome-executable",
        default=None,
        help="Optional Chrome/Chromium executable path for Playwright to launch.",
    )
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    evidence = run_browser_verification(
        repo_root=repo_root,
        fixture_name=args.fixture,
        expected_score=args.expected_score,
        screenshot_path=repo_root / args.screenshot,
        log_path=repo_root / args.log,
        executable_path=args.chrome_executable,
        timeout_ms=args.timeout_ms,
    )
    write_evidence(evidence, repo_root / args.evidence)
    print(json.dumps(asdict(evidence), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
