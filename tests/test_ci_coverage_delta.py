from __future__ import annotations

import json
from pathlib import Path

from scripts import ci_coverage_delta


def test_main_writes_missing_report_payload_when_coverage_xml_absent(
    monkeypatch, tmp_path: Path
) -> None:
    missing_xml = tmp_path / "coverage.xml"
    output = tmp_path / "coverage-delta.json"

    monkeypatch.setenv("COVERAGE_XML_PATH", str(missing_xml))
    monkeypatch.setenv("OUTPUT_PATH", str(output))

    exit_code = ci_coverage_delta.main()

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "missing-report"
    assert payload["reason"] == "coverage-xml-not-found"
    assert payload["coverage_xml_path"] == str(missing_xml)
