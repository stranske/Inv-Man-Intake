"""Verify the static operator demo in a real headless browser and write evidence artifacts."""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_EXPECTED_SCORE = "0.7809"
DEFAULT_OUTPUT_DIR = Path("app/live-verification-artifacts")
DEFAULT_SCREENSHOT_NAME = "browser-demo-score.png"
DEFAULT_LOG_NAME = "browser-demo-score.json"
PYODIDE_VERSION = "0.26.2"
REQUIRED_PYODIDE_FILES = [
    "pyodide.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
]
REQUIRED_PYODIDE_WHEEL_PATTERNS = [
    "micropip-*.whl",
    "packaging-*.whl",
    "numpy-*.whl",
    "pandas-*.whl",
    "pillow-*.whl",
    "protobuf-*.whl",
]


@dataclass(frozen=True)
class BrowserVerificationResult:
    status: str
    verified_at: str
    url: str
    expected_score: str
    page_title: str
    screenshot_path: str
    log_path: str
    body_excerpt: str
    console_messages: list[dict[str, str]]
    failed_requests: list[dict[str, str]]
    page_errors: list[str]
    external_requests: list[str]


@dataclass(frozen=True)
class OfflineVerificationResult:
    status: str
    checked_at: str
    index_path: str
    pyodide_vendor: str
    app_runtime: str
    dependency_closure: list[str]


def canonical_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def assert_non_empty_file(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"Missing required offline runtime file: {path}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"Offline runtime file is empty: {path}")


def assert_glob_has_non_empty_files(directory: Path, pattern: str) -> None:
    matches = sorted(directory.glob(pattern))
    if not matches:
        raise RuntimeError(f"Missing required offline wheel matching {directory / pattern}")
    empty = [str(path) for path in matches if path.stat().st_size == 0]
    if empty:
        raise RuntimeError(f"Offline wheel files are empty: {', '.join(empty)}")


def assert_index_has_no_external_urls(index_path: Path) -> None:
    source = index_path.read_text(encoding="utf-8")
    external_runtime_refs = [
        match.group(0)
        for match in re.finditer(
            r"""<(?:script|link)\b[^>]+(?:src|href)=["']https?://[^"']+["']""",
            source,
        )
    ]
    external_imports = [
        match.group(0)
        for match in re.finditer(
            r"""\bimport(?:\s*\(|\s+[^;]*?\s+from\s+)["']https?://[^"']+["']""",
            source,
        )
    ]
    external_urls = sorted(set(re.findall(r"https?://[^\"'`\s<>]+", source)))

    if external_runtime_refs or external_imports or external_urls:
        details = external_runtime_refs + external_imports + external_urls
        raise RuntimeError("index.html contains external URL references: " + ", ".join(details))
    expected_pyodide_path = f"./vendor/pyodide@{PYODIDE_VERSION}/pyodide.js"
    if expected_pyodide_path not in source:
        raise RuntimeError(
            "index.html must point at the local "
            f"./vendor/pyodide@{PYODIDE_VERSION}/pyodide.js runtime"
        )
    if "stlite.mount" in source or "vendor/stlite" in source or "streamlit_app.py" in source:
        raise RuntimeError("index.html must use the static SPA/Pyodide runtime, not stlite")
    if 'data-app-runtime="static-spa-pyodide"' not in source:
        raise RuntimeError("index.html is missing the static-spa-pyodide runtime marker")


def pyodide_dependency_closure(pyodide_vendor: Path) -> list[str]:
    lock_path = pyodide_vendor / "pyodide-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("packages", {})
    packages_by_name = {
        canonical_package_name(package.get("name", key)): package
        for key, package in packages.items()
    }
    local_wheels = {path.name for path in pyodide_vendor.glob("*.whl")}
    seed = {
        canonical_package_name(package.get("name", key))
        for key, package in packages.items()
        if package.get("file_name") in local_wheels
    }
    seed.update({canonical_package_name("micropip"), canonical_package_name("packaging")})

    closure: set[str] = set()
    stack = sorted(seed)
    while stack:
        package_name = stack.pop()
        if package_name in closure:
            continue
        closure.add(package_name)
        package = packages_by_name.get(package_name)
        if package is None:
            raise RuntimeError(f"Package {package_name} is missing from pyodide-lock.json")
        for dependency in package.get("depends", []):
            canonical_dependency = canonical_package_name(dependency)
            if canonical_dependency not in closure:
                stack.append(canonical_dependency)

    missing_files = []
    for package_name in sorted(closure):
        file_name = packages_by_name[package_name].get("file_name")
        if file_name and not (pyodide_vendor / file_name).is_file():
            missing_files.append(f"{package_name}: {file_name}")
    if missing_files:
        raise RuntimeError(
            "Pyodide dependency closure is not fully vendored; missing " + ", ".join(missing_files)
        )

    return sorted(closure)


def verify_offline_runtime(repo_root: Path) -> OfflineVerificationResult:
    repo_root = repo_root.resolve()
    index_path = repo_root / "app" / "index.html"
    pyodide_vendor = repo_root / "app" / "vendor" / f"pyodide@{PYODIDE_VERSION}"

    assert_index_has_no_external_urls(index_path)
    assert_non_empty_file(repo_root / "app" / "static_operator_app.js")
    assert_non_empty_file(repo_root / "app" / "pyodide_packet_bridge.py")
    for relative_path in REQUIRED_PYODIDE_FILES:
        assert_non_empty_file(pyodide_vendor / relative_path)
    for pattern in REQUIRED_PYODIDE_WHEEL_PATTERNS:
        assert_glob_has_non_empty_files(pyodide_vendor, pattern)

    dependency_closure = pyodide_dependency_closure(pyodide_vendor)
    return OfflineVerificationResult(
        status="pass",
        checked_at=datetime.now(UTC).isoformat(),
        index_path=str(index_path.relative_to(repo_root)),
        pyodide_vendor=str(pyodide_vendor.relative_to(repo_root)),
        app_runtime="static-spa-pyodide",
        dependency_closure=dependency_closure,
    )


def find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def build_artifact_paths(output_dir: Path) -> tuple[Path, Path]:
    return output_dir / DEFAULT_SCREENSHOT_NAME, output_dir / DEFAULT_LOG_NAME


def start_static_server(repo_root: Path, port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def is_local_browser_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in {"about", "blob", "data"}:
        return True
    if parsed.scheme in {"http", "https"}:
        return parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    return parsed.scheme == ""


def handle_offline_route(route: Any, external_requests: list[str]) -> None:
    request_url = route.request.url
    if is_local_browser_url(request_url):
        route.continue_()
        return
    external_requests.append(request_url)
    route.abort()


def verify_browser_demo(
    *,
    repo_root: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    expected_score: str = DEFAULT_EXPECTED_SCORE,
    timeout_ms: int = 45_000,
    browser_channel: str | None = "chrome",
    offline: bool = False,
) -> BrowserVerificationResult:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by CLI users.
        raise RuntimeError(
            "Playwright is required for browser verification. Install dev dependencies and run "
            "`python -m playwright install chromium`, or use a system Chrome channel."
        ) from exc

    repo_root = repo_root.resolve()
    output_dir = (repo_root / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path, log_path = build_artifact_paths(output_dir)
    port = find_free_port()
    url = f"http://127.0.0.1:{port}/app/index.html"
    server = start_static_server(repo_root, port)
    console_messages: list[dict[str, str]] = []
    failed_requests: list[dict[str, str]] = []
    page_errors: list[str] = []
    external_requests: list[str] = []

    try:
        time.sleep(0.5)
        with sync_playwright() as playwright:
            launch_kwargs: dict[str, Any] = {"headless": True}
            if browser_channel:
                launch_kwargs["channel"] = browser_channel
            browser = playwright.chromium.launch(**launch_kwargs)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                if offline:
                    page.route("**/*", lambda route: handle_offline_route(route, external_requests))
                page.on(
                    "console",
                    lambda msg: console_messages.append(
                        {"type": msg.type, "text": msg.text[:1000]}
                    ),
                )
                page.on("pageerror", lambda exc: page_errors.append(str(exc)[:2000]))
                page.on(
                    "requestfailed",
                    lambda request: failed_requests.append(
                        {"url": request.url, "failure": str(request.failure)}
                    ),
                )
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.get_by_text("Inv-Man-Intake").wait_for(timeout=timeout_ms)
                page.get_by_text("Final score").wait_for(timeout=timeout_ms)
                page.get_by_text(expected_score).wait_for(timeout=timeout_ms)
                page.screenshot(path=str(screenshot_path), full_page=True)
                body_text = page.locator("body").inner_text(timeout=timeout_ms)
                if external_requests:
                    result = BrowserVerificationResult(
                        status="fail",
                        verified_at=datetime.now(UTC).isoformat(),
                        url=url,
                        expected_score=expected_score,
                        page_title=page.title(),
                        screenshot_path=str(screenshot_path.relative_to(repo_root)),
                        log_path=str(log_path.relative_to(repo_root)),
                        body_excerpt=body_text[:1200],
                        console_messages=console_messages,
                        failed_requests=failed_requests,
                        page_errors=page_errors,
                        external_requests=external_requests,
                    )
                    log_path.write_text(
                        json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8"
                    )
                    raise RuntimeError(
                        "Offline stlite verification attempted external requests: "
                        + ", ".join(sorted(set(external_requests)))
                    )
                result = BrowserVerificationResult(
                    status="pass",
                    verified_at=datetime.now(UTC).isoformat(),
                    url=url,
                    expected_score=expected_score,
                    page_title=page.title(),
                    screenshot_path=str(screenshot_path.relative_to(repo_root)),
                    log_path=str(log_path.relative_to(repo_root)),
                    body_excerpt=body_text[:1200],
                    console_messages=console_messages,
                    failed_requests=failed_requests,
                    page_errors=page_errors,
                    external_requests=external_requests,
                )
            except PlaywrightTimeoutError as exc:
                page.screenshot(path=str(screenshot_path), full_page=True)
                body_text = page.locator("body").inner_text(timeout=5_000)
                result = BrowserVerificationResult(
                    status="fail",
                    verified_at=datetime.now(UTC).isoformat(),
                    url=url,
                    expected_score=expected_score,
                    page_title=page.title(),
                    screenshot_path=str(screenshot_path.relative_to(repo_root)),
                    log_path=str(log_path.relative_to(repo_root)),
                    body_excerpt=body_text[:1200],
                    console_messages=console_messages,
                    failed_requests=failed_requests,
                    page_errors=page_errors,
                    external_requests=external_requests,
                )
                log_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
                raise RuntimeError(
                    f"Timed out waiting for stlite demo to render Final score {expected_score} "
                    f"at {url}. Wrote failure evidence to {log_path.relative_to(repo_root)} "
                    f"and {screenshot_path.relative_to(repo_root)}."
                ) from exc
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    log_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--expected-score", default=DEFAULT_EXPECTED_SCORE)
    parser.add_argument("--timeout-ms", type=int, default=45_000)
    parser.add_argument(
        "--browser-channel",
        default="chrome",
        help="Playwright Chromium channel to use. Pass an empty string to use bundled Chromium.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run network-free static offline runtime checks instead of browser verification.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.offline:
        try:
            result = verify_offline_runtime(args.repo_root)
        except RuntimeError as exc:
            print(f"Offline stlite verification failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(asdict(result), indent=2))
        return 0

    browser_channel = args.browser_channel or None
    result = verify_browser_demo(
        repo_root=args.repo_root,
        output_dir=args.output_dir,
        expected_score=args.expected_score,
        timeout_ms=args.timeout_ms,
        browser_channel=browser_channel,
        offline=False,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
