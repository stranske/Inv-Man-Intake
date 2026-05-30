"""Same-business-day throughput readiness check for the v1 smoke pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from inv_man_intake.observability import TraceEvent
from inv_man_intake.v1_smoke import run_v1_smoke_pipeline

DEFAULT_FIXTURE_ROOT = Path("tests/fixtures/intake")
DEFAULT_BATCH_PACKAGES = (
    {
        "intake_bundle_file": "pdf_primary_mixed_bundle.json",
        "package_id": "pkg_pdf_mixed_001",
        "expected_document_ids": (
            "pkg_pdf_mixed_001:doc:0",
            "pkg_pdf_mixed_001:doc:1",
            "pkg_pdf_mixed_001:doc:2",
            "pkg_pdf_mixed_001:doc:3",
        ),
    },
    {
        "intake_bundle_file": "pptx_primary_mixed_bundle.json",
        "package_id": "pkg_pptx_mixed_001",
        "expected_document_ids": (
            "pkg_pptx_mixed_001:doc:0",
            "pkg_pptx_mixed_001:doc:1",
            "pkg_pptx_mixed_001:doc:2",
        ),
    },
)
DEFAULT_OUTPUT_PATH = Path("reports/readiness/throughput_readiness.json")
MIN_PACKAGES_PER_WEEK = 10
TARGET_PACKAGES_PER_WEEK = 15
BUSINESS_DAYS_PER_WEEK = 5
SAME_BUSINESS_DAY_SECONDS = 8 * 60 * 60
SYNTHETIC_LOWER_BOUND_WARNING = (
    "synthetic lower bound: fixture timing excludes real extraction and IO cost"
)
STAGE_EVENT_NAMES = {
    "intake": ("v1_acceptance.intake_register",),
    "extraction_thresholds": (
        "extraction_orchestrator.run",
        "v1_acceptance.threshold_handling",
    ),
    "performance_normalization": ("v1_acceptance.performance_normalize",),
    "queue_audit_output": ("v1_acceptance.queue_audit_output",),
    "scoring": ("v1_acceptance.scoring_compute",),
}


@dataclass(frozen=True)
class StageTiming:
    """Elapsed wall time for one readiness stage."""

    stage: str
    duration_ms: float


@dataclass(frozen=True)
class ReadinessReport:
    """Machine-readable throughput readiness result."""

    status: str
    package_count: int
    document_count: int
    score_count: int
    escalation_count: int
    target_packages_per_week: str
    same_business_day_target_seconds: int
    observed_total_seconds: float
    projected_packages_per_business_day: float
    synthetic_lower_bound: bool
    stage_timings: list[StageTiming]
    bottleneck_warnings: list[str]
    report_path: str

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def run_readiness_check(output_path: Path = DEFAULT_OUTPUT_PATH) -> ReadinessReport:
    """Run the offline v1 fixture batch and write an ephemeral readiness report."""

    artifacts_batch = [
        run_v1_smoke_pipeline(
            fixture_root=DEFAULT_FIXTURE_ROOT,
            intake_bundle_file=cast(str, package["intake_bundle_file"]),
            package_id=cast(str, package["package_id"]),
            expected_document_ids=cast(tuple[str, ...], package["expected_document_ids"]),
        )
        for package in DEFAULT_BATCH_PACKAGES
    ]

    trace_events: list[TraceEvent] = []
    document_count = 0
    score_count = 0
    escalation_count = 0
    for artifacts in artifacts_batch:
        record = cast(Any, artifacts.record)
        score = cast(Any, artifacts.score)
        threshold_decision = cast(Any, artifacts.threshold_decision)
        conflict_result = cast(Any, artifacts.conflict_result)
        secondary_extraction_result = cast(Any, artifacts.secondary_extraction_result)
        trace_events.extend(artifacts.sink.events)
        document_count += len(record.document_ids)
        score_count += 1 if score.final_score is not None else 0
        escalation_count += _escalation_count(
            extraction_escalates=threshold_decision.escalate,
            conflict_escalates=conflict_result.escalate,
            secondary_escalates=not secondary_extraction_result.resolved,
        )

    report = build_readiness_report(
        trace_events=trace_events,
        document_count=document_count,
        score_count=score_count,
        escalation_count=escalation_count,
        output_path=output_path,
        package_count=len(DEFAULT_BATCH_PACKAGES),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_report_payload(report), indent=2) + "\n", encoding="utf-8")
    return report


def build_readiness_report(
    *,
    trace_events: list[TraceEvent],
    document_count: int,
    score_count: int,
    escalation_count: int,
    output_path: Path,
    package_count: int = 1,
) -> ReadinessReport:
    """Build a readiness report from v1 smoke trace events."""

    stage_timings = [
        StageTiming(stage=stage, duration_ms=_duration_for_events(trace_events, names))
        for stage, names in STAGE_EVENT_NAMES.items()
    ]
    missing_stages = [timing.stage for timing in stage_timings if timing.duration_ms <= 0]
    observed_total_seconds = round(
        sum(timing.duration_ms for timing in stage_timings) / 1000,
        6,
    )
    projected_packages_per_business_day = _project_packages_per_business_day(observed_total_seconds)
    bottleneck_warnings = _bottleneck_warnings(
        missing_stages=missing_stages,
        score_count=score_count,
        observed_total_seconds=observed_total_seconds,
        projected_packages_per_business_day=projected_packages_per_business_day,
    )
    status = "pass" if not _blocking_warnings(bottleneck_warnings) else "fail"
    return ReadinessReport(
        status=status,
        package_count=package_count,
        document_count=document_count,
        score_count=score_count,
        escalation_count=escalation_count,
        target_packages_per_week=f"{MIN_PACKAGES_PER_WEEK}-{TARGET_PACKAGES_PER_WEEK}",
        same_business_day_target_seconds=SAME_BUSINESS_DAY_SECONDS,
        observed_total_seconds=observed_total_seconds,
        projected_packages_per_business_day=projected_packages_per_business_day,
        synthetic_lower_bound=True,
        stage_timings=stage_timings,
        bottleneck_warnings=bottleneck_warnings,
        report_path=str(output_path),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Ephemeral report path. Default: {DEFAULT_OUTPUT_PATH}",
    )
    args = parser.parse_args(argv)
    report = run_readiness_check(output_path=args.output)
    print(json.dumps(_report_payload(report), indent=2))
    return 0 if report.passed else 1


def _report_payload(report: ReadinessReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["stage_timings"] = [asdict(timing) for timing in report.stage_timings]
    return payload


def _duration_for_events(trace_events: list[TraceEvent], names: tuple[str, ...]) -> float:
    durations = []
    for name in names:
        duration = _total_completed_duration_ms(trace_events, name)
        if duration <= 0:
            return 0.0
        durations.append(duration)
    return round(sum(durations), 3)


def _total_completed_duration_ms(trace_events: list[TraceEvent], name: str) -> float:
    starts_by_span_id: dict[str, list[TraceEvent]] = {}
    total_duration = 0.0
    for event in trace_events:
        if event.name != name:
            continue
        if event.ended_at is None:
            starts_by_span_id.setdefault(event.span_id, []).append(event)
            continue
        starts = starts_by_span_id.get(event.span_id)
        if not starts:
            continue
        start = starts.pop(0)
        started_at = datetime.fromisoformat(start.started_at)
        ended_at = datetime.fromisoformat(event.ended_at)
        duration = (ended_at - started_at).total_seconds() * 1000
        if duration > 0:
            total_duration += duration
    return round(total_duration, 3)


def _escalation_count(
    *,
    extraction_escalates: bool,
    conflict_escalates: bool,
    secondary_escalates: bool,
) -> int:
    return sum(
        1
        for escalates in (extraction_escalates, conflict_escalates, secondary_escalates)
        if escalates
    )


def _project_packages_per_business_day(observed_total_seconds: float) -> float:
    if observed_total_seconds <= 0:
        return 0.0
    return round(SAME_BUSINESS_DAY_SECONDS / observed_total_seconds, 2)


def _bottleneck_warnings(
    *,
    missing_stages: list[str],
    score_count: int,
    observed_total_seconds: float,
    projected_packages_per_business_day: float,
) -> list[str]:
    warnings = [SYNTHETIC_LOWER_BOUND_WARNING]
    if missing_stages:
        warnings.append(f"missing timing evidence for stages: {', '.join(missing_stages)}")
    if score_count < 1:
        warnings.append("scoring stage produced no verifiable scores")
    if observed_total_seconds <= 0:
        warnings.append("readiness run produced no measurable elapsed time")
    if observed_total_seconds > SAME_BUSINESS_DAY_SECONDS:
        warnings.append("fixture batch exceeds same-business-day target")
    projected_packages_per_week = projected_packages_per_business_day * BUSINESS_DAYS_PER_WEEK
    if projected_packages_per_week < MIN_PACKAGES_PER_WEEK:
        warnings.append("projected weekly capacity is below 10 packages/week target")
    return warnings


def _blocking_warnings(warnings: list[str]) -> list[str]:
    return [warning for warning in warnings if warning != SYNTHETIC_LOWER_BOUND_WARNING]


if __name__ == "__main__":
    raise SystemExit(main())
