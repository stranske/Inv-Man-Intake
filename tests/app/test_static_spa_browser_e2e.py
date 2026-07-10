"""Live browser coverage for the local static operator SPA."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.request import urlopen

import pytest

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


def test_static_spa_upload_renders_accessible_coverage() -> None:
    """A real packet upload produces a browser-visible coverage result."""

    with local_static_spa() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.get_by_role("heading", name="Packet upload").wait_for(timeout=45_000)

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
        finally:
            browser.close()
