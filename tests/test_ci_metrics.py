from __future__ import annotations

import json
from pathlib import Path

from scripts import ci_metrics


def test_ci_metrics_main_writes_skipped_payload_when_junit_missing(
    monkeypatch: object, tmp_path: Path
) -> None:
    output_path = tmp_path / "ci-metrics.json"
    missing_junit = tmp_path / "missing-junit.xml"

    monkeypatch.setenv("JUNIT_PATH", str(missing_junit))  # type: ignore[attr-defined]
    monkeypatch.setenv("OUTPUT_PATH", str(output_path))  # type: ignore[attr-defined]

    rc = ci_metrics.main()

    assert rc == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert payload["reason"] == "missing-junit-report"
    assert payload["junit_path"] == str(missing_junit)
    assert payload["summary"]["tests"] == 0
