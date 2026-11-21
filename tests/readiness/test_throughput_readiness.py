from __future__ import annotations

import json
from pathlib import Path

import pytest

from inv_man_intake.observability import TraceEvent
from inv_man_intake.readiness.throughput import (
    STAGE_EVENT_NAMES,
    SYNTHETIC_LOWER_BOUND_WARNING,
    _bottleneck_warnings,
    _duration_for_events,
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
    assert payload["package_count"] == 2
    assert payload["document_count"] == 7
    assert payload["score_count"] == 2
    assert payload["escalation_count"] == 5
    assert {item["stage"] for item in payload["stage_timings"]} == set(STAGE_EVENT_NAMES)
    assert all(item["duration_ms"] > 0 for item in payload["stage_timings"])
    assert payload["target_packages_per_week"] == "10-15"
    assert payload["same_business_day_target_seconds"] == 28800
    assert payload["projected_packages_per_business_day"] >= 10
    assert payload["synthetic_lower_bound"] is True
    assert SYNTHETIC_LOWER_BOUND_WARNING in payload["bottleneck_warnings"]


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
    assert SYNTHETIC_LOWER_BOUND_WARNING in report.bottleneck_warnings


def test_fixture_run_is_marked_synthetic_lower_bound(tmp_path: Path) -> None:
    output_path = tmp_path / "throughput_readiness.json"

    report = run_readiness_check(output_path=output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert report.synthetic_lower_bound is True
    assert payload["synthetic_lower_bound"] is True
    assert SYNTHETIC_LOWER_BOUND_WARNING in report.bottleneck_warnings
    assert SYNTHETIC_LOWER_BOUND_WARNING in payload["bottleneck_warnings"]


def test_duration_for_events_sums_completed_spans_by_name() -> None:
    events = [
        _trace_event("shared-stage", "span-a", "2026-05-10T00:00:00+00:00"),
        _trace_event("shared-stage", "span-b", "2026-05-10T00:00:10+00:00"),
        _trace_event(
            "shared-stage", "span-b", "2026-05-10T00:00:10+00:00", "2026-05-10T00:00:11+00:00"
        ),
        _trace_event(
            "shared-stage", "span-a", "2026-05-10T00:00:00+00:00", "2026-05-10T00:00:30+00:00"
        ),
    ]

    assert _duration_for_events(events, ("shared-stage",)) == 31000.0


def test_bottleneck_warning_projects_business_day_capacity_to_weekly_target() -> None:
    warnings = _bottleneck_warnings(
        missing_stages=[],
        score_count=1,
        observed_total_seconds=1,
        projected_packages_per_business_day=2,
    )

    assert "projected weekly capacity is below 10 packages/week target" not in warnings


def test_throughput_readiness_cli_returns_success(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "cli_readiness.json"

    exit_code = main(["--output", str(output_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output_path.exists()
    assert '"status": "pass"' in captured.out


def _trace_event(
    name: str,
    span_id: str,
    started_at: str,
    ended_at: str | None = None,
) -> TraceEvent:
    return TraceEvent(
        kind="span",
        span_id=span_id,
        trace_id="trace-1",
        run_id=None,
        name=name,
        parent_run_id=None,
        parent_span_id=None,
        metadata={},
        started_at=started_at,
        ended_at=ended_at,
    )


def test_throughput_measures_production_real_byte_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measure a bundled real-byte batch through production extraction and output writes.

    Input: the checked-in conforming Doc-Lineage PDF and the real XLSX track record, staged as
    external-layout packages and run through the supported ``run_pipeline`` entry point.
    Control: the fixture smoke check keeps its own mode, synthetic label and stage reporting.
    """

    from inv_man_intake import v1_smoke
    from inv_man_intake.readiness import throughput

    def legacy_fixture_service():
        raise AssertionError("production batch must not use build_legacy_pdf_fixture_service")

    output_path = tmp_path / "production_batch.json"
    work_dir = tmp_path / "work"

    # Forbidden only for the production run; the smoke control below legitimately uses it.
    with monkeypatch.context() as production_patch:
        production_patch.setattr(
            v1_smoke, "build_legacy_pdf_fixture_service", legacy_fixture_service
        )
        report = throughput.run_production_batch_check(output_path=output_path, work_dir=work_dir)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    package_count = len(throughput.PRODUCTION_BATCH_PACKAGES)
    assert package_count == 2
    assert report.passed is True
    assert payload["status"] == "pass"
    assert payload["mode"] == "production_real_bytes"
    assert payload["synthetic_lower_bound"] is False
    assert payload["package_count"] == package_count
    assert payload["document_count"] == 2 * package_count
    # Real batch wall time, measured around run_pipeline, not summed smoke stage spans.
    assert payload["elapsed_seconds"] > 0
    assert payload["input_bytes"] == package_count * (
        Path("tests/fixtures/extraction/summit_arc_investment_update_conforming.pdf").stat().st_size
        + Path("tests/fixtures/extraction/summit_arc_track_record.xlsx").stat().st_size
    )
    outcomes = payload["outcome_counts"]
    assert sum(outcomes.values()) == package_count
    assert outcomes["failed"] == 0
    assert outcomes["auto_pass"] + outcomes["escalated"] == package_count
    assert payload["measured_packages_per_hour"] == pytest.approx(
        package_count / payload["elapsed_seconds"] * 3600, rel=0.01
    )
    assert payload["measured_packages_per_business_day"] == pytest.approx(
        package_count / payload["elapsed_seconds"] * throughput.SAME_BUSINESS_DAY_SECONDS,
        rel=0.01,
    )
    # No smoke stage timings or synthetic caveat leak into the real-byte report.
    assert "stage_timings" not in payload
    assert SYNTHETIC_LOWER_BOUND_WARNING not in payload["bottleneck_warnings"]

    # Emitted artifacts verify the production extractor and the output writes actually ran.
    assert payload["production_extractor_verified"] is True
    assert "doc-lineage:text_layer" in payload["extraction_methods"]
    assert payload["verified_outputs"] is True
    assert len(payload["packages"]) == package_count
    for entry in payload["packages"]:
        package_dir = work_dir / "output" / entry["package_id"]
        run = json.loads((package_dir / "run.json").read_text(encoding="utf-8"))
        assert run["inputs"]["package_id"] == entry["package_id"]
        assert run["provenance"]["provider"] != "fixture-fallback"
        assert "doc-lineage:text_layer" in {field["method"] for field in run["fields"]}
        assert entry["outcome"] in {"auto_pass", "escalated"}
        assert entry["output_files"] > 5
        for artifact in ("metadata.json", "threshold-summary.json", "validation-queue.json"):
            assert (package_dir / artifact).stat().st_size > 0
        assert (package_dir / "manifest.json").is_file()

    # Compatibility control: the smoke check is unchanged and distinctly labelled.
    smoke_path = tmp_path / "smoke.json"
    smoke = run_readiness_check(output_path=smoke_path)
    smoke_payload = json.loads(smoke_path.read_text(encoding="utf-8"))
    assert smoke_payload["mode"] == "fixture_smoke"
    assert smoke_payload["synthetic_lower_bound"] is True
    assert smoke_payload["package_count"] == 2
    assert smoke_payload["document_count"] == 7
    assert smoke_payload["score_count"] == 2
    assert smoke_payload["escalation_count"] == 5
    assert {item["stage"] for item in smoke_payload["stage_timings"]} == set(STAGE_EVENT_NAMES)
    assert SYNTHETIC_LOWER_BOUND_WARNING in smoke.bottleneck_warnings
    assert "elapsed_seconds" not in smoke_payload
    assert "outcome_counts" not in smoke_payload
    assert smoke_payload["mode"] != payload["mode"]


def test_production_batch_cli_mode_keeps_smoke_default(tmp_path: Path, capsys) -> None:
    smoke_path = tmp_path / "smoke.json"
    assert main(["--output", str(smoke_path)]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "fixture_smoke"

    batch_path = tmp_path / "batch.json"
    exit_code = main(["--mode", "production-batch", "--output", str(batch_path)])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "production_real_bytes"
    assert json.loads(batch_path.read_text(encoding="utf-8"))["status"] == "pass"
