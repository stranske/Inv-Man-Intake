"""Live browser coverage for the local static operator SPA."""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.request import urlopen

import pytest
from scripts.verify_static_spa_pyodide import handle_offline_route

playwright_sync = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync.sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PACKET_FIXTURE = ROOT / "tests" / "fixtures" / "intake" / "pdf_primary_mixed_bundle.json"


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def local_static_spa() -> Iterator[str]:
    """Serve the committed SPA bundle from a local-only HTTP endpoint."""

    port = _free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}/app/index.html"
    try:
        for _ in range(50):
            try:
                with urlopen(url, timeout=0.2):  # noqa: S310 - fixed loopback URL
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("local static SPA server did not become ready")
        yield url
    finally:
        server.terminate()
        server.wait(timeout=5)


def _verify_static_spa_interactions(page: object) -> None:
    """Exercise upload, graphic, and escalation paths through accessible browser UI."""

    page.locator("#packet-upload").set_input_files(str(PACKET_FIXTURE))
    upload_count = page.locator("#upload-count")
    upload_count.wait_for(timeout=45_000)
    assert upload_count.text_content() == "Uploaded file count: 1"

    coverage_table = page.get_by_role("table", name="Packet coverage results")
    coverage_row = coverage_table.get_by_role(
        "row", name="upload_1 fixture_packet manager, fees, returns, graphics"
    )
    coverage_row.wait_for(timeout=45_000)
    assert coverage_row.is_visible()
    runtime_status = page.get_by_role("status").first
    assert (
        "Pyodide packet pipeline ready (deterministic-browser-bridge)."
        in runtime_status.text_content()
    )
    assert page.locator("main").get_attribute("data-packet-path") == "deterministic-browser-bridge"

    page.get_by_role("button", name="Open graphic").first.click()
    graphics_table = page.get_by_role("table", name="Packet graphics")
    assert re.search(r"Opened", graphics_table.inner_text(timeout=45_000))

    page.get_by_role("button", name="Seed deterministic conflict").click()
    queue_table = page.get_by_role("table", name="Exception queue")
    seeded_row = queue_table.get_by_role(
        "row",
        name="Seeded deterministic conflict Browser-verification escalation Operations review",
    )
    assert seeded_row.count() == 1


def _with_page(
    test_controls: dict[str, bool] | None = None,
    *,
    enforce_local_requests: bool = False,
) -> tuple[object, object, object, object, list[str]]:
    """Open the static SPA with optional test-only handler controls."""

    server_context = local_static_spa()
    url = server_context.__enter__()
    playwright_context = sync_playwright()
    playwright = playwright_context.__enter__()
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page()
    external_requests: list[str] = []
    if enforce_local_requests:
        # This is deliberately registered before navigation so initial Pyodide
        # bootstrap requests cannot bypass the no-egress assertion.
        page.route("**/*", lambda route: handle_offline_route(route, external_requests))
    if test_controls:
        page.add_init_script(f"window.__STATIC_SPA_TEST_CONTROLS__ = {json.dumps(test_controls)};")
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    page.get_by_role("heading", name="Packet upload").wait_for(timeout=45_000)
    return server_context, playwright_context, browser, page, external_requests


def _close_page(server_context: object, playwright_context: object, browser: object) -> None:
    browser.close()
    playwright_context.__exit__(None, None, None)
    server_context.__exit__(None, None, None)


def test_static_spa_offline_upload_runs_local_pyodide_packet_path_without_egress() -> None:
    """The full initial-load path is local-only and runs the deterministic Pyodide bridge."""

    server_context, playwright_context, browser, page, external_requests = _with_page(
        enforce_local_requests=True
    )
    try:
        _verify_static_spa_interactions(page)
        assert external_requests == []
    finally:
        _close_page(server_context, playwright_context, browser)


@pytest.mark.parametrize("control", ["disableGraphicHandler", "disableConflictHandler"])
def test_static_spa_deliberate_break_fails_the_interaction_assertion(control: str) -> None:
    """Disabling either concrete handler makes the same browser path fail."""

    server_context, playwright_context, browser, page, _ = _with_page({control: True})
    try:
        with pytest.raises(AssertionError):
            _verify_static_spa_interactions(page)
    finally:
        _close_page(server_context, playwright_context, browser)
