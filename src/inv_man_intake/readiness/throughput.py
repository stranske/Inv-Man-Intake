"""Same-business-day throughput readiness checks for the v1 pipeline.

Two distinct modes are reported separately and never mixed:

* ``fixture_smoke`` (default): the synthetic smoke batch. Its timings are a lower bound that
  excludes real extraction and IO cost.
* ``production_real_bytes`` (``--mode production-batch``): a small bundled real-byte corpus run
  through the production ``run_pipeline`` entry point (Doc-Lineage extraction plus the output
  artifact writes). Elapsed time, outcome counts and throughput are measured wall-clock values.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict, cast

from inv_man_intake.observability import TraceEvent
from inv_man_intake.readiness.fixture_batches import DEFAULT_BATCH_PACKAGES
from inv_man_intake.run import ARTIFACT_MANIFEST, ARTIFACT_RUN, run_pipeline
from inv_man_intake.v1_smoke import run_v1_smoke_pipeline

DEFAULT_FIXTURE_ROOT = Path("tests/fixtures/intake")
DEFAULT_OUTPUT_PATH = Path("reports/readiness/throughput_readiness.json")
DEFAULT_PRODUCTION_CORPUS_ROOT = Path("tests/fixtures/extraction")
DEFAULT_PRODUCTION_OUTPUT_PATH = Path("reports/readiness/throughput_production_batch.json")
MODE_FIXTURE_SMOKE = "fixture_smoke"
MODE_PRODUCTION_REAL_BYTES = "production_real_bytes"
OUTCOME_AUTO_PASS = "auto_pass"
OUTCOME_ESCALATED = "escalated"
OUTCOME_FAILED = "failed"
PRODUCTION_EXTRACTOR_METHOD_PREFIX = "doc-lineage:"
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
    mode: str = MODE_FIXTURE_SMOKE

    @property
    def passed(self) -> bool:
        return self.status == "pass"


class ProductionBatchFile(TypedDict):
    file_name: str
    role: str


class ProductionBatchPackage(TypedDict):
    package_id: str
    firm_name: str
    fund_name: str
    received_at: str
    files: tuple[ProductionBatchFile, ...]


_PRODUCTION_BATCH_FILES: tuple[ProductionBatchFile, ...] = (
    {"file_name": "summit_arc_investment_update_conforming.pdf", "role": "investment_deck"},
    {"file_name": "summit_arc_track_record.xlsx", "role": "performance_track_record"},
)

# Small bundled real-byte corpus: checked-in conforming PDF and XLSX bytes (no synthetic
# fixture parsing) staged as external-layout packages for the production entry point.
PRODUCTION_BATCH_PACKAGES: tuple[ProductionBatchPackage, ...] = (
    {
        "package_id": "pkg_readiness_real_001",
        "firm_name": "Summit Arc Advisors",
        "fund_name": "Summit Arc Special Situations",
        "received_at": "2026-03-04T08:20:00Z",
        "files": _PRODUCTION_BATCH_FILES,
    },
    {
        "package_id": "pkg_readiness_real_002",
        "firm_name": "Summit Arc Advisors",
        "fund_name": "Summit Arc Special Situations II",
        "received_at": "2026-03-05T08:20:00Z",
        "files": _PRODUCTION_BATCH_FILES,
    },
)


@dataclass(frozen=True)
class ProductionPackageResult:
    """Measured outcome for one real-byte package."""

    package_id: str
    outcome: str
    document_count: int
    input_bytes: int
    output_files: int
    extraction_methods: list[str]
    error: str | None = None


@dataclass(frozen=True)
class ProductionBatchReport:
    """Measured (non-synthetic) throughput for a real-byte production batch."""

    status: str
    mode: str
    package_count: int
    document_count: int
    input_bytes: int
    elapsed_seconds: float
    outcome_counts: dict[str, int]
    measured_packages_per_hour: float
    measured_packages_per_business_day: float
    target_packages_per_week: str
    same_business_day_target_seconds: int
    synthetic_lower_bound: bool
    production_extractor_verified: bool
    extraction_methods: list[str]
    verified_outputs: bool
    bottleneck_warnings: list[str]
    packages: list[ProductionPackageResult]
    report_path: str

    @property
    def passed(self) -> bool:
        return self.status == "pass"


def run_readiness_check(output_path: Path = DEFAULT_OUTPUT_PATH) -> ReadinessReport:
    """Run the offline v1 fixture batch and write an ephemeral readiness report."""

    artifacts_batch = [
        run_v1_smoke_pipeline(
            fixture_root=DEFAULT_FIXTURE_ROOT,
            intake_bundle_file=package["intake_bundle_file"],
            package_id=package["package_id"],
            expected_document_ids=package["expected_document_ids"],
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


def run_production_batch_check(
    output_path: Path = DEFAULT_PRODUCTION_OUTPUT_PATH,
    *,
    corpus_root: Path = DEFAULT_PRODUCTION_CORPUS_ROOT,
    packages: tuple[ProductionBatchPackage, ...] = PRODUCTION_BATCH_PACKAGES,
    work_dir: Path | None = None,
) -> ProductionBatchReport:
    """Run the bundled real-byte corpus through ``run_pipeline`` and measure the batch.

    Staging copies are made before the clock starts; the measured interval covers only the
    production entry points (intake, extraction, thresholds, scoring and artifact writes).
    ``work_dir`` keeps staged inputs and emitted artifacts for inspection; by default they
    live in a temporary directory removed after the report is written.
    """

    if work_dir is not None:
        report = _measure_production_batch(
            output_path=output_path, corpus_root=corpus_root, packages=packages, work_dir=work_dir
        )
    else:
        with tempfile.TemporaryDirectory(prefix="inv-man-throughput-") as temp_dir:
            report = _measure_production_batch(
                output_path=output_path,
                corpus_root=corpus_root,
                packages=packages,
                work_dir=Path(temp_dir),
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8")
    return report


def _measure_production_batch(
    *,
    output_path: Path,
    corpus_root: Path,
    packages: tuple[ProductionBatchPackage, ...],
    work_dir: Path,
) -> ProductionBatchReport:
    staged = [
        (package, _stage_production_package(package, corpus_root, work_dir / "corpus"))
        for package in packages
    ]
    output_root = work_dir / "output"

    results: list[ProductionPackageResult] = []
    started = time.perf_counter()
    for package, (bundle_path, input_bytes) in staged:
        package_id = package["package_id"]
        results.append(
            _run_production_package(
                package_id=package_id,
                bundle_path=bundle_path,
                input_bytes=input_bytes,
                output_dir=output_root / package_id,
            )
        )
    elapsed_seconds = round(time.perf_counter() - started, 6)

    outcome_counts = {
        outcome: sum(1 for result in results if result.outcome == outcome)
        for outcome in (OUTCOME_AUTO_PASS, OUTCOME_ESCALATED, OUTCOME_FAILED)
    }
    completed = [result for result in results if result.outcome != OUTCOME_FAILED]
    methods = sorted({method for result in completed for method in result.extraction_methods})
    # Every package must carry at least one field attributed to the production extractor;
    # derived fields (e.g. threshold summaries) carry their own non-extractor method labels.
    production_verified = (
        bool(completed)
        and len(completed) == len(results)
        and all(
            any(
                method.startswith(PRODUCTION_EXTRACTOR_METHOD_PREFIX)
                for method in r.extraction_methods
            )
            for r in completed
        )
    )
    verified_outputs = bool(completed) and len(completed) == len(results)
    for result in completed:
        verified_outputs = verified_outputs and _outputs_are_verified(
            output_root / result.package_id
        )

    per_second = len(results) / elapsed_seconds if elapsed_seconds > 0 else 0.0
    per_business_day = round(per_second * SAME_BUSINESS_DAY_SECONDS, 2)
    warnings = _production_batch_warnings(
        outcome_counts=outcome_counts,
        elapsed_seconds=elapsed_seconds,
        production_verified=production_verified,
        verified_outputs=verified_outputs,
        packages_per_business_day=per_business_day,
        errors=[f"{result.package_id}: {result.error}" for result in results if result.error],
    )
    return ProductionBatchReport(
        status="pass" if not warnings else "fail",
        mode=MODE_PRODUCTION_REAL_BYTES,
        package_count=len(results),
        document_count=sum(result.document_count for result in results),
        input_bytes=sum(result.input_bytes for result in results),
        elapsed_seconds=elapsed_seconds,
        outcome_counts=outcome_counts,
        measured_packages_per_hour=round(per_second * 3600, 2),
        measured_packages_per_business_day=per_business_day,
        target_packages_per_week=f"{MIN_PACKAGES_PER_WEEK}-{TARGET_PACKAGES_PER_WEEK}",
        same_business_day_target_seconds=SAME_BUSINESS_DAY_SECONDS,
        synthetic_lower_bound=False,
        production_extractor_verified=production_verified,
        extraction_methods=methods,
        verified_outputs=verified_outputs,
        bottleneck_warnings=warnings,
        packages=results,
        report_path=str(output_path),
    )


def _stage_production_package(
    package: ProductionBatchPackage, corpus_root: Path, staging_root: Path
) -> tuple[Path, int]:
    package_dir = staging_root / package["package_id"]
    package_dir.mkdir(parents=True, exist_ok=True)
    input_bytes = 0
    for entry in package["files"]:
        target = package_dir / entry["file_name"]
        shutil.copyfile(corpus_root / entry["file_name"], target)
        input_bytes += target.stat().st_size
    bundle = {
        "package_id": package["package_id"],
        "metadata": {
            "firm_name": package["firm_name"],
            "fund_name": package["fund_name"],
            "received_at": package["received_at"],
            "source_channel": "internal_forward",
        },
        "files": [
            {
                "file_name": entry["file_name"],
                "role": entry["role"],
                "source_ref": f"readiness:{package['package_id']}",
            }
            for entry in package["files"]
        ],
    }
    bundle_path = package_dir / "intake_bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return bundle_path, input_bytes


def _run_production_package(
    *, package_id: str, bundle_path: Path, input_bytes: int, output_dir: Path
) -> ProductionPackageResult:
    # Only data-level rejections become a "failed" outcome. A missing or broken extraction
    # dependency (RuntimeError / ModuleNotFoundError) propagates so the batch fails visibly.
    try:
        result = run_pipeline(bundle_path, output_dir=output_dir)
    except (ValueError, OSError) as exc:
        return ProductionPackageResult(
            package_id=package_id,
            outcome=OUTCOME_FAILED,
            document_count=0,
            input_bytes=input_bytes,
            output_files=_count_files(output_dir),
            extraction_methods=[],
            error=f"{type(exc).__name__}: {exc}",
        )
    escalated = bool(result.escalation_state.get("escalate"))
    return ProductionPackageResult(
        package_id=package_id,
        outcome=OUTCOME_ESCALATED if escalated else OUTCOME_AUTO_PASS,
        document_count=len(result.inputs["document_ids"]),
        input_bytes=input_bytes,
        output_files=_count_files(output_dir),
        extraction_methods=sorted({str(field["method"]) for field in result.fields}),
    )


def _count_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.iterdir() if path.is_file())


def _outputs_are_verified(output_dir: Path) -> bool:
    try:
        run = json.loads((output_dir / ARTIFACT_RUN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    refs = run.get("artifact_refs")
    if not isinstance(refs, list) or not refs:
        return False
    expected = [*refs, ARTIFACT_MANIFEST]
    return all(
        (output_dir / name).is_file() and (output_dir / name).stat().st_size > 0
        for name in expected
    )


def _production_batch_warnings(
    *,
    outcome_counts: dict[str, int],
    elapsed_seconds: float,
    production_verified: bool,
    verified_outputs: bool,
    packages_per_business_day: float,
    errors: list[str],
) -> list[str]:
    warnings: list[str] = []
    if outcome_counts[OUTCOME_FAILED]:
        warnings.append(f"{outcome_counts[OUTCOME_FAILED]} package(s) failed production ingest")
        warnings.extend(errors)
    if elapsed_seconds <= 0:
        warnings.append("production batch produced no measurable elapsed time")
    if not production_verified:
        warnings.append("production extractor output could not be verified from emitted artifacts")
    if not verified_outputs:
        warnings.append("production output artifacts could not be verified on disk")
    if packages_per_business_day * BUSINESS_DAYS_PER_WEEK < MIN_PACKAGES_PER_WEEK:
        warnings.append("measured weekly capacity is below 10 packages/week target")
    return warnings


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
        "--mode",
        choices=("smoke", "production-batch"),
        default="smoke",
        help=(
            "smoke: synthetic fixture lower bound (default). production-batch: measured "
            "real-byte corpus through the production extractor and output writes."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Ephemeral report path. Default: "
            f"{DEFAULT_OUTPUT_PATH} (smoke) or {DEFAULT_PRODUCTION_OUTPUT_PATH} (production-batch)"
        ),
    )
    args = parser.parse_args(argv)
    if args.mode == "production-batch":
        batch_report = run_production_batch_check(
            output_path=args.output or DEFAULT_PRODUCTION_OUTPUT_PATH
        )
        print(json.dumps(asdict(batch_report), indent=2))
        return 0 if batch_report.passed else 1
    report = run_readiness_check(output_path=args.output or DEFAULT_OUTPUT_PATH)
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
