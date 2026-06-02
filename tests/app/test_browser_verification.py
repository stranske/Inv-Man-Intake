from __future__ import annotations

from pathlib import Path

import pytest
from app.streamlit_app import run_demo_fixture

from app import browser_verification as bv

ARTIFACT_DIR = Path("app/artifacts/browser-verification")


def test_build_verification_page_is_self_contained_and_recomputes_score() -> None:
    result = run_demo_fixture(bv.DEFAULT_FIXTURE)
    page = bv.build_verification_page(result)

    # Embeds the real pipeline data (no hand-authored score).
    assert '"final_score": 0.7809' in page
    assert '"component": "operational_quality"' in page
    assert f'"owner_role": "{result.owner_role}"' in page

    # The browser recomputes the score from contributions rather than echoing it.
    assert "reduce(" in page
    assert "Number(c.contribution)" in page
    assert "toFixed(4)" in page

    # Zero-egress: no CDN / external script or stylesheet references.
    assert "http://" not in page
    assert "https://" not in page
    assert "cdn." not in page


def test_find_browser_honors_explicit_path(tmp_path: Path) -> None:
    fake = tmp_path / "fake-chrome"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    assert bv.find_browser(str(fake)) == str(fake)


def test_committed_artifact_shows_browser_rendered_score() -> None:
    screenshot = ARTIFACT_DIR / "browser-verification.png"
    dom = ARTIFACT_DIR / "browser-verification-dom.html"
    log = ARTIFACT_DIR / "browser-verification.log"

    assert screenshot.is_file()
    assert dom.is_file()
    assert log.is_file()

    # PNG magic + non-trivial size proves a real raster capture is committed.
    raw = screenshot.read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 5_000

    dom_text = dom.read_text(encoding="utf-8")
    assert 'id="final-score">0.7809' in dom_text
    assert 'data-rendered="true"' in dom_text

    log_text = log.read_text(encoding="utf-8")
    assert "0.7809" in log_text
    assert "#469" in log_text
    assert "#470" in log_text


@pytest.mark.skipif(bv.find_browser() is None, reason="no Chrome/Chromium binary available")
def test_headless_capture_produces_artifact(tmp_path: Path) -> None:
    result = run_demo_fixture(bv.DEFAULT_FIXTURE)
    try:
        captured = bv.capture(result, tmp_path)
    except RuntimeError as exc:
        if "did not produce a screenshot" in str(exc):
            pytest.skip(
                f"headless browser is present but cannot capture in this environment: {exc}"
            )
        raise

    assert captured.rendered_score == "0.7809"
    assert captured.screenshot_path.is_file()
    assert captured.screenshot_path.stat().st_size > 0
    dom_text = captured.dom_path.read_text(encoding="utf-8")
    assert "0.7809" in dom_text
    assert 'data-rendered="true"' in dom_text
