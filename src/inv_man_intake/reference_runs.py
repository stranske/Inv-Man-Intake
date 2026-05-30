"""Golden reference runs for the deterministic extraction-threshold decision core.

The acceptance smoke (:mod:`inv_man_intake.v1_smoke`) and the throughput
readiness check both exercise a *single* escalate-shaped package
(``pkg_pdf_mixed_001`` / ``pkg_pptx_mixed_001``), so the decision branches in
:func:`inv_man_intake.extraction.confidence.evaluate_thresholds` that a triage
tool must never silently regress -- ``auto_pass_document`` vs
``missing_mandatory_field:*`` vs ``confidence_below_threshold:*`` -- have no
named, drift-detecting golden coverage.

This module builds **golden reference runs** for those branches. Each scenario
is a synthetic field bundle (``tests/fixtures/intake/reference_*_bundle.json``)
fed through the real ``evaluate_thresholds`` + ``attach_threshold_summary``
decision core. The deterministic, redaction-safe subset of the result (the
threshold decision plus per-field ``key``/``confidence``/``source_page``, with
field *values* stripped) is serialized with ``json.dumps(..., sort_keys=True)``
-- the same stable-writer pattern used by ``run.py`` and ``langsmith_fleet`` --
and compared byte-for-byte against a committed golden in
``tests/fixtures/golden/``.

Privacy / data-zone note: this path is the local deterministic core with zero
LLM/network involvement. The bundles are synthetic fixtures (no real proprietary
values) and the serialized golden subset strips field values regardless, so
nothing sensitive is committed.

Regenerate the committed goldens after an intentional decision-contract change::

    python -m inv_man_intake.reference_runs --regenerate
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from inv_man_intake.extraction.confidence import (
    ThresholdConfig,
    attach_threshold_summary,
    evaluate_thresholds,
)
from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
)

REFERENCE_SCHEMA_VERSION = "reference-run/v1"
REFERENCE_PROVIDER_NAME = "reference-synthetic"

FIXTURE_ROOT = Path("tests/fixtures/intake")
GOLDEN_ROOT = Path("tests/fixtures/golden")

# Scenario bundle file -> committed golden file. The three entries cover the
# distinct decision branches of ``evaluate_thresholds`` that are not already
# pinned by the single escalate-shaped acceptance smoke fixture.
REFERENCE_SCENARIOS: tuple[tuple[str, str], ...] = (
    ("reference_auto_pass_bundle.json", "reference_auto_pass_run.json"),
    ("reference_missing_mandatory_bundle.json", "reference_missing_mandatory_run.json"),
    (
        "reference_confidence_below_threshold_bundle.json",
        "reference_confidence_below_threshold_run.json",
    ),
)


def load_bundle(path: Path) -> dict[str, Any]:
    """Load and shallowly validate a synthetic reference scenario bundle."""

    bundle = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict):
        raise ValueError(f"reference bundle root must be a JSON object: {path}")
    for required in ("scenario_id", "package_id", "source_doc_id", "key_fields", "fields"):
        if required not in bundle:
            raise ValueError(f"reference bundle {path} missing required key: {required}")
    if "threshold_config" not in bundle:
        raise ValueError(f"reference bundle {path} missing threshold_config")
    return bundle


def _threshold_config(bundle: dict[str, Any]) -> ThresholdConfig:
    raw = bundle["threshold_config"]
    return ThresholdConfig(
        field_auto_accept_min=float(raw["field_auto_accept_min"]),
        key_field_confidence_min=float(raw["key_field_confidence_min"]),
        document_key_field_coverage_min=float(raw["document_key_field_coverage_min"]),
        mandatory_field_min=float(raw["mandatory_field_min"]),
        mandatory_fields=tuple(raw["mandatory_fields"]),
    )


def _extracted_result(bundle: dict[str, Any]) -> ExtractedDocumentResult:
    source_doc_id = str(bundle["source_doc_id"])
    fields = tuple(
        ExtractedField(
            key=str(field["key"]),
            value=str(field["value"]),
            confidence=float(field["confidence"]),
            source_doc_id=source_doc_id,
            source_page=int(field["source_page"]),
            method=REFERENCE_PROVIDER_NAME,
        )
        for field in bundle["fields"]
    )
    return ExtractedDocumentResult(
        source_doc_id=source_doc_id,
        fields=fields,
        provider_name=REFERENCE_PROVIDER_NAME,
    )


def build_reference_run(bundle: dict[str, Any]) -> dict[str, Any]:
    """Run a synthetic scenario through the real threshold-decision core.

    Returns the deterministic, redaction-safe golden subset: the threshold
    decision plus the per-field ``key``/``confidence``/``source_page`` inputs
    (field *values* stripped) and the decision-derived threshold-summary fields.
    """

    config = _threshold_config(bundle)
    result = _extracted_result(bundle)
    key_fields = tuple(str(key) for key in bundle["key_fields"])

    decision = evaluate_thresholds(result=result, key_fields=key_fields, config=config)
    with_summary = attach_threshold_summary(result=result, decision=decision)

    input_keys = {field.key for field in result.fields}
    summary_fields = [
        {"key": field.key, "value": field.value}
        for field in with_summary.fields
        if field.key not in input_keys
    ]

    return {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "scenario_id": str(bundle["scenario_id"]),
        "package_id": str(bundle["package_id"]),
        "source_doc_id": result.source_doc_id,
        "provider_name": result.provider_name,
        "key_fields": sorted(key_fields),
        "decision": {
            "auto_pass_document": decision.auto_pass_document,
            "escalate": decision.escalate,
            "escalation_reason": decision.escalation_reason or "none",
            "key_field_coverage_ratio": round(decision.key_field_coverage_ratio, 4),
            "auto_accept_fields": sorted(decision.auto_accept_fields),
        },
        # Redaction-safe per-field subset: deterministic decision inputs only,
        # field values deliberately stripped. Sorted for stable goldens.
        "fields": [
            {
                "key": field.key,
                "confidence": field.confidence,
                "source_page": field.source_page,
            }
            for field in sorted(result.fields, key=lambda item: item.key)
        ],
        "threshold_summary_fields": sorted(summary_fields, key=lambda item: item["key"]),
    }


def serialize_reference_run(payload: dict[str, Any]) -> str:
    """Serialize a reference run to its stable on-disk form (sorted keys)."""

    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def iter_reference_runs(*, fixture_root: Path = FIXTURE_ROOT) -> list[tuple[str, dict[str, Any]]]:
    """Build every committed reference scenario; returns ``(golden_name, payload)``."""

    runs: list[tuple[str, dict[str, Any]]] = []
    for bundle_name, golden_name in REFERENCE_SCENARIOS:
        bundle = load_bundle(fixture_root / bundle_name)
        runs.append((golden_name, build_reference_run(bundle)))
    return runs


def regenerate_goldens(
    *, fixture_root: Path = FIXTURE_ROOT, golden_root: Path = GOLDEN_ROOT
) -> list[Path]:
    """Write the committed goldens for every scenario; returns written paths."""

    golden_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for golden_name, payload in iter_reference_runs(fixture_root=fixture_root):
        path = golden_root / golden_name
        path.write_text(serialize_reference_run(payload), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Overwrite the committed goldens in tests/fixtures/golden/.",
    )
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=FIXTURE_ROOT,
        help=f"Scenario bundle directory. Default: {FIXTURE_ROOT}",
    )
    parser.add_argument(
        "--golden-root",
        type=Path,
        default=GOLDEN_ROOT,
        help=f"Committed golden directory. Default: {GOLDEN_ROOT}",
    )
    args = parser.parse_args(argv)

    if args.regenerate:
        written = regenerate_goldens(fixture_root=args.fixture_root, golden_root=args.golden_root)
        for path in written:
            print(f"wrote {path}")
        return 0

    for golden_name, payload in iter_reference_runs(fixture_root=args.fixture_root):
        print(f"# {golden_name}")
        print(serialize_reference_run(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
