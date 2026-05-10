from __future__ import annotations

import json
from pathlib import Path

from inv_man_intake.readiness.throughput import (
    STAGE_EVENT_NAMES,
    build_readiness_report,
    main,
    run_readiness_check,
)


def test_throughput_readiness_writes_report_with_required_fields(tmp_path: Path) -> None:
    output_path = tmp_path / "throughput_readiness.json"

    report = run_readiness_check(output_path=output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert report.passed is True
    assert payload["status"] == "pass"
    assert payload["package_count"] == 1
    assert payload["document_count"] == 4
    assert payload["score_count"] == 1
    assert payload["escalation_count"] == 3
    assert {item["stage"] for item in payload["stage_timings"]} == set(STAGE_EVENT_NAMES)
    assert all(item["duration_ms"] > 0 for item in payload["stage_timings"])
    assert payload["target_packages_per_week"] == "10-15"
    assert payload["same_business_day_target_seconds"] == 28800
    assert payload["projected_packages_per_business_day"] >= 10


def test_throughput_readiness_fails_when_stage_output_is_missing(tmp_path: Path) -> None:
    report = build_readiness_report(
        trace_events=[],
        document_count=0,
        score_count=0,
        escalation_count=0,
        output_path=tmp_path / "missing.json",
    )

    assert report.status == "fail"
    assert "scoring stage produced no verifiable scores" in report.bottleneck_warnings
    assert any("missing timing evidence" in warning for warning in report.bottleneck_warnings)


def test_throughput_readiness_cli_returns_success(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "cli_readiness.json"

    exit_code = main(["--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_path.exists()
    assert '"status": "pass"' in captured.out
