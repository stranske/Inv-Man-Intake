"""Headless intake run entry point: ``package -> run.json + named artifacts``.

This module exposes :func:`run_pipeline`, the reusable core that executes the
deterministic intake -> extraction -> thresholds -> performance -> queue ->
scoring path for an arbitrary intake bundle and writes a single replayable
``run.json`` plus the three already-named artifact files
(``metadata.json``, ``threshold-summary.json``, ``explainability.json``) into
an operator-supplied output directory.

The orchestration itself lives in :func:`inv_man_intake.v1_smoke._run_pipeline_core`,
which the acceptance smoke (``run_v1_smoke_pipeline``) also delegates to, so the
operator CLI and the smoke test share one code path.

Privacy / data-zone note: the deterministic core (intake,
``PdfPrimaryExtractionProvider``, thresholds, scoring) has zero data egress and
may run on real proprietary packages locally. ``run.json`` is a full per-run
artifact carrying field values, so it is written only to the operator-supplied
``output_dir`` and is never emitted to the fleet telemetry NDJSON sink, which
enforces its own redaction denylist.
"""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from inv_man_intake.extraction.confidence import ThresholdDecision, load_threshold_config
from inv_man_intake.extraction.providers.base import SnippetMetadata, SourceLocation
from inv_man_intake.intake.integration import IntakeRegistrationResult
from inv_man_intake.intake.models import IngestRecord
from inv_man_intake.observability.tracing import TraceContext
from inv_man_intake.run_manifest import MANIFEST_NAME, build_manifest
from inv_man_intake.scoring.contracts import ScoreResult
from inv_man_intake.v1_smoke import V1SmokeArtifacts, _pipeline_latency_ms, _run_pipeline_core

_ROOT_SPAN_NAME = "v1_acceptance.intake_register"

ARTIFACT_RUN = "run.json"
ARTIFACT_METADATA = "metadata.json"
ARTIFACT_THRESHOLD = "threshold-summary.json"
ARTIFACT_EXPLAINABILITY = "explainability.json"
ARTIFACT_MANIFEST = MANIFEST_NAME
DEFAULT_THRESHOLD_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "extraction_thresholds.yaml"


@dataclass(frozen=True)
class RunResult:
    """Replayable per-run record produced by :func:`run_pipeline`.

    Every field is concretely typed (no bare ``object``) and JSON-serializable.
    :meth:`to_json` returns a plain ``dict`` whose deterministic on-disk form is
    produced with ``json.dumps(..., sort_keys=True)``.
    """

    run_id: str
    inputs: dict[str, Any]
    fields: list[dict[str, Any]]
    confidence_state: dict[str, Any]
    escalation_state: dict[str, Any]
    final_score: float
    explainability: dict[str, Any]
    warnings: list[str]
    latency_ms: int | None
    provenance: dict[str, Any]
    trace_refs: list[str]
    artifact_refs: list[str]
    manifest: str

    def to_json(self) -> dict[str, Any]:
        """Return the run record as a JSON-serializable dictionary."""

        return {
            "schema_version": "run-contract/v1",
            "repo": "stranske/Inv-Man-Intake",
            "tool": "inv-man-ingest",
            "run_id": self.run_id,
            "status": "success",
            "github_issue": "stranske/Inv-Man-Intake#474",
            "actor": {
                "kind": "ci",
                "id": "inv-man-ingest-reference-run",
                "intent": "headless intake-to-score run",
            },
            "inputs": {
                **self.inputs,
                "validated": True,
                "refs": [f"ref:package:{self.inputs['package_id']}"],
            },
            "outputs": {
                "manifest_ref": self.manifest,
                "artifact_ids": [Path(ref).name for ref in self.artifact_refs],
                "summary": {
                    "final_score": self.final_score,
                    "escalation_reason": self.escalation_state["reason"],
                    "field_count": len(self.fields),
                },
            },
            "fields": self.fields,
            "confidence_state": self.confidence_state,
            "escalation_state": self.escalation_state,
            "final_score": self.final_score,
            "explainability": self.explainability,
            "warnings": [
                {"code": warning, "severity": "warning", "message": warning}
                for warning in self.warnings
            ],
            "evidence_refs": sorted(
                {
                    f"document:{field['source_doc_id']}#page={field['source_page']}"
                    for field in self.fields
                    if field.get("source_doc_id") and field.get("source_page") is not None
                }
            ),
            "identity_refs": [
                f"firm:{self.inputs['firm_id']}",
                f"fund:{self.inputs['fund_id']}",
            ],
            "latency_ms": self.latency_ms,
            "latency": {"wall_ms": self.latency_ms or 0},
            "provenance": self.provenance,
            "trace_refs": self.trace_refs,
            "artifact_refs": self.artifact_refs,
            "manifest": self.manifest,
        }


def run_pipeline(
    bundle_path: Path,
    *,
    output_dir: Path,
    threshold_config_path: Path | None = None,
) -> RunResult:
    """Run the intake pipeline for ``bundle_path`` and write artifacts to ``output_dir``.

    Returns the :class:`RunResult`. Writes ``run.json`` plus the three named
    artifact files into ``output_dir`` (created if missing).

    Raises:
        ValueError: The bundle is malformed, declares no usable ``package_id``,
            or is rejected by intake validation.
        OSError: The bundle or output artifact paths cannot be read or written.
    """

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if not isinstance(bundle, dict):
        raise ValueError("intake bundle root must be a JSON object")
    package_id = bundle.get("package_id")
    if not isinstance(package_id, str) or not package_id.strip():
        raise ValueError("intake bundle must declare a non-empty string package_id")

    threshold_config = load_threshold_config(threshold_config_path or DEFAULT_THRESHOLD_CONFIG_PATH)
    artifacts = _run_pipeline_core(
        fixture_root=bundle_path.parent,
        intake_bundle_file=bundle_path.name,
        package_id=package_id,
        threshold_config=threshold_config,
    )
    result = _build_run_result(artifacts)
    _write_run_artifacts(result=result, artifacts=artifacts, output_dir=output_dir)
    return result


def _build_run_result(artifacts: V1SmokeArtifacts) -> RunResult:
    record = cast(IngestRecord, artifacts.record)
    score = cast(ScoreResult, artifacts.score)
    decision = cast(ThresholdDecision, artifacts.threshold_decision)
    trace_context = cast(TraceContext, artifacts.trace_context)
    registration = cast(IntakeRegistrationResult, artifacts.registration)
    extraction = artifacts.extraction_with_thresholds

    fields = [
        {
            "key": field.key,
            "value": field.value,
            "confidence": field.confidence,
            "source_doc_id": field.source_doc_id,
            "source_page": field.source_page,
            "method": field.method,
            "location": _source_location_payload(field.location),
            "snippet": field.snippet,
            "snippet_metadata": _snippet_metadata_payload(field.snippet_metadata),
        }
        for field in extraction.fields
    ]
    evidence = {
        field.key: {
            "source_doc_id": field.source_doc_id,
            "source_page": field.source_page,
            "confidence": field.confidence,
            "method": field.method,
            "location": _source_location_payload(field.location),
            "snippet": field.snippet,
            "snippet_metadata": _snippet_metadata_payload(field.snippet_metadata),
        }
        for field in extraction.fields
    }

    return RunResult(
        run_id=trace_context.run_id or trace_context.trace_id,
        inputs={
            "package_id": record.package_id,
            "firm_id": record.firm_id,
            "fund_id": record.fund_id,
            "file_count": record.file_count,
            "status": record.status,
            "document_ids": list(record.document_ids),
        },
        fields=fields,
        confidence_state={
            "key_field_coverage_ratio": decision.key_field_coverage_ratio,
            "auto_pass_document": decision.auto_pass_document,
            "auto_accept_fields": list(decision.auto_accept_fields),
        },
        escalation_state={
            "escalate": decision.escalate,
            "reason": decision.escalation_reason or "none",
            "auto_pass_document": decision.auto_pass_document,
        },
        final_score=score.final_score,
        explainability=dict(artifacts.formatted_explainability),
        warnings=_collect_warnings(registration=registration, decision=decision),
        latency_ms=_pipeline_latency_ms(sink=artifacts.sink, root_span_name=_ROOT_SPAN_NAME),
        provenance={
            "tool_version": _tool_version(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "tool": "inv-man-ingest",
            "provider": extraction.provider_name,
            "evidence": evidence,
        },
        trace_refs=[f"trace:{trace_context.trace_id}"],
        artifact_refs=[
            ARTIFACT_RUN,
            ARTIFACT_METADATA,
            ARTIFACT_THRESHOLD,
            ARTIFACT_EXPLAINABILITY,
        ],
        manifest=f"artifact:{ARTIFACT_MANIFEST}",
    )


def _source_location_payload(location: SourceLocation | None) -> dict[str, object] | None:
    if location is None:
        return None
    return {
        "source_doc_id": location.source_doc_id,
        "source_page": location.source_page,
        "bbox": list(location.bbox) if location.bbox is not None else None,
        "table_index": location.table_index,
        "image_index": location.image_index,
    }


def _snippet_metadata_payload(metadata: SnippetMetadata | None) -> dict[str, object] | None:
    if metadata is None:
        return None
    return {
        "kind": metadata.kind,
        "char_start": metadata.char_start,
        "char_end": metadata.char_end,
    }


def _collect_warnings(
    *,
    registration: IntakeRegistrationResult,
    decision: ThresholdDecision,
) -> list[str]:
    warnings = [f"intake:{issue.code}" for issue in registration.warnings]
    if decision.escalate and decision.escalation_reason:
        warnings.append(f"threshold:{decision.escalation_reason}")
    return sorted(warnings)


def _tool_version() -> str:
    try:
        return version("inv-man-intake")
    except PackageNotFoundError:
        return "0.0+local"


def _build_metadata(artifacts: V1SmokeArtifacts) -> dict[str, Any]:
    record = cast(IngestRecord, artifacts.record)
    repository = artifacts.core_repository
    documents: list[dict[str, Any]] = []
    for document_id in record.document_ids:
        document = repository.get_document(document_id)
        if document is None:
            documents.append({"document_id": document_id})
            continue
        documents.append(
            {
                "document_id": document_id,
                "file_name": document.file_name,
                "file_hash": document.file_hash,
                "fund_id": document.fund_id,
                "received_at": document.received_at,
                "source_channel": document.source_channel,
            }
        )
    return {
        "package_id": record.package_id,
        "firm_id": record.firm_id,
        "fund_id": record.fund_id,
        "file_count": record.file_count,
        "status": record.status,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "documents": documents,
    }


def _build_threshold_summary(artifacts: V1SmokeArtifacts) -> dict[str, Any]:
    decision = cast(ThresholdDecision, artifacts.threshold_decision)
    extraction = artifacts.extraction_with_thresholds
    document_fields = {
        field.key: field.value
        for field in extraction.fields
        if field.key.startswith("confidence.document.")
    }
    return {
        "document": document_fields,
        "key_field_coverage_ratio": decision.key_field_coverage_ratio,
        "auto_pass_document": decision.auto_pass_document,
        "escalate": decision.escalate,
        "escalation_reason": decision.escalation_reason or "none",
        "auto_accept_fields": list(decision.auto_accept_fields),
    }


def _write_run_artifacts(
    *,
    result: RunResult,
    artifacts: V1SmokeArtifacts,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = [
        output_dir / ARTIFACT_RUN,
        output_dir / ARTIFACT_METADATA,
        output_dir / ARTIFACT_THRESHOLD,
        output_dir / ARTIFACT_EXPLAINABILITY,
    ]
    _write_json(written[0], result.to_json())
    _write_json(written[1], _build_metadata(artifacts))
    _write_json(written[2], _build_threshold_summary(artifacts))
    _write_json(written[3], dict(artifacts.formatted_explainability))

    # Hash the artifacts as actually written (run.json already carries its
    # ``manifest`` pointer), then record them in a deterministic manifest.json.
    trace_context = cast(TraceContext, artifacts.trace_context)
    manifest = build_manifest(
        run_id=result.run_id,
        trace_id=trace_context.trace_id,
        artifacts=written,
    )
    _write_json(output_dir / ARTIFACT_MANIFEST, manifest)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
