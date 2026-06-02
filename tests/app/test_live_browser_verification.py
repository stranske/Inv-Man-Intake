from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_stlite_browser_demo import BrowserEvidence, write_evidence


def test_browser_evidence_json_records_real_browser_contract(tmp_path: Path) -> None:
    evidence = BrowserEvidence(
        url="http://127.0.0.1:8765/app/index.html",
        fixture_name="pdf_primary_mixed_bundle.json",
        expected_score="0.7809",
        observed_score="0.7809",
        screenshot_path="app/live-verification-browser.png",
        browser_log_path="app/live-verification-browser.log",
        selector_checks={
            "title": True,
            "fixture": True,
            "score": True,
            "explainability": True,
            "analyst_queue": True,
        },
    )

    output = tmp_path / "live-verification-browser.json"
    write_evidence(evidence, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["fixture_name"] == "pdf_primary_mixed_bundle.json"
    assert payload["observed_score"] == "0.7809"
    assert payload["screenshot_path"] == "app/live-verification-browser.png"
    assert all(payload["selector_checks"].values())


def test_browser_verifier_script_documents_default_artifacts() -> None:
    script = Path("scripts/verify_stlite_browser_demo.py").read_text(encoding="utf-8")

    assert "app/live-verification-browser.png" in script
    assert "app/live-verification-browser.log" in script
    assert "app/live-verification-browser.json" in script
    assert "pdf_primary_mixed_bundle.json" in script
    assert "0.7809" in script
    assert "get_by_text(expected_score)" in script
