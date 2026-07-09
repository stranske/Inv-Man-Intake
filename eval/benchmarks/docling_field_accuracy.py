"""Run Docling field-accuracy evaluation against rotating fixture samples."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inv_man_intake.extraction.evaluation.field_accuracy import (
    EvaluationSample,
    FieldAccuracyReport,
    FieldExpectation,
    evaluate_field_accuracy,
)
from inv_man_intake.extraction.providers.base import ExtractionProvider
from inv_man_intake.extraction.providers.docling_primary import (
    DoclingPrimaryExtractionProvider,
    MissingDoclingDependencyError,
)

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "docling_samples"
_MANIFEST_PATH = _FIXTURE_ROOT / "manifest.json"
_EXPECTED_PATH = _FIXTURE_ROOT / "expected_results.json"


@dataclass(frozen=True)
class BenchmarkSample:
    """Repository fixture metadata plus expected extracted fields."""

    sample_id: str
    source_path: Path
    expected_fields: tuple[FieldExpectation, ...]


def load_samples(
    *,
    manifest_path: Path = _MANIFEST_PATH,
    expected_path: Path = _EXPECTED_PATH,
    repo_root: Path = _ROOT,
) -> tuple[BenchmarkSample, ...]:
    """Load benchmark samples from the committed manifest and expected-results files."""

    manifest = _load_json_object(manifest_path)
    expected = _load_json_object(expected_path)
    sample_entries = manifest.get("samples")
    if not isinstance(sample_entries, list) or not sample_entries:
        raise ValueError("manifest must contain a non-empty samples list")

    samples: list[BenchmarkSample] = []
    for entry in sample_entries:
        if not isinstance(entry, dict):
            raise ValueError("manifest samples must be objects")
        sample_id = _required_str(entry, "sample_id")
        source_path = repo_root / _required_str(entry, "source_path")
        expected_entry = expected.get(sample_id)
        if not isinstance(expected_entry, dict):
            raise ValueError(f"missing expected results for {sample_id}")
        expected_fields = expected_entry.get("expected_fields")
        if not isinstance(expected_fields, dict) or not expected_fields:
            raise ValueError(f"expected_fields for {sample_id} must be a non-empty object")
        samples.append(
            BenchmarkSample(
                sample_id=sample_id,
                source_path=source_path,
                expected_fields=tuple(
                    FieldExpectation(key=str(key), value=str(value))
                    for key, value in expected_fields.items()
                ),
            )
        )
    return tuple(samples)


def select_rotating_sample(
    samples: Sequence[BenchmarkSample],
    *,
    sample_index: int,
) -> BenchmarkSample:
    """Select one sample by modulo index so scheduled jobs can rotate deterministically."""

    if not samples:
        raise ValueError("at least one benchmark sample is required")
    return samples[sample_index % len(samples)]


def samples_to_evaluation(samples: Sequence[BenchmarkSample]) -> tuple[EvaluationSample, ...]:
    """Read sample bytes and adapt benchmark metadata to the shared evaluator."""

    evaluation_samples: list[EvaluationSample] = []
    for sample in samples:
        if not sample.source_path.exists():
            raise FileNotFoundError(f"missing benchmark sample: {sample.source_path}")
        evaluation_samples.append(
            EvaluationSample(
                source_doc_id=sample.sample_id,
                content=sample.source_path.read_bytes(),
                expected_fields=sample.expected_fields,
            )
        )
    return tuple(evaluation_samples)


def run_benchmark(
    *,
    provider: ExtractionProvider,
    samples: Sequence[BenchmarkSample],
) -> FieldAccuracyReport:
    """Run the selected samples and return the shared field-accuracy report."""

    return evaluate_field_accuracy(
        provider_factory=lambda: provider,
        samples=samples_to_evaluation(samples),
    )


def format_report(report: FieldAccuracyReport) -> str:
    """Format the required stdout metric."""

    return f"field_accuracy: {report.accuracy:.2f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-id", help="Run one sample by id.")
    parser.add_argument(
        "--sample-index",
        type=int,
        default=int(os.environ.get("IMI_DOCLING_EVAL_SAMPLE_INDEX", "0")),
        help="Modulo index used to rotate one sample when --all and --sample-id are omitted.",
    )
    parser.add_argument("--all", action="store_true", help="Run every committed benchmark sample.")
    args = parser.parse_args(argv)

    try:
        samples = load_samples()
        selected = _select_samples(samples=samples, sample_id=args.sample_id, all_samples=args.all, sample_index=args.sample_index)
        report = run_benchmark(provider=DoclingPrimaryExtractionProvider(), samples=selected)
    except MissingDoclingDependencyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(format_report(report))
    if report.missing_fields:
        print("missing_fields: " + ", ".join(report.missing_fields))
    if report.mismatched_fields:
        print("mismatched_fields: " + ", ".join(report.mismatched_fields))
    return 0


def _select_samples(
    *,
    samples: Sequence[BenchmarkSample],
    sample_id: str | None,
    all_samples: bool,
    sample_index: int,
) -> tuple[BenchmarkSample, ...]:
    if all_samples:
        return tuple(samples)
    if sample_id is None:
        return (select_rotating_sample(samples, sample_index=sample_index),)
    for sample in samples:
        if sample.sample_id == sample_id:
            return (sample,)
    raise ValueError(f"unknown sample id: {sample_id}")


def _load_json_object(path: Path) -> dict[str, Any]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parsed


def _required_str(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"manifest sample is missing {key}")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
