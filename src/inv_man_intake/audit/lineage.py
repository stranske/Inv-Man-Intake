"""Regulatory lineage packet assembly for one intake scoring decision."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from inv_man_intake.data.models import Document
from inv_man_intake.data.provenance import CorrectionRecord, ExtractedFieldRecord
from inv_man_intake.extraction.confidence import ThresholdDecision
from inv_man_intake.scoring.contracts import ScoreResult


def build_lineage_packet(
    *,
    run_id: str,
    manifest_ref: str,
    documents: Sequence[Document],
    extracted_fields: Sequence[ExtractedFieldRecord],
    correction_history: Mapping[str, Sequence[CorrectionRecord]],
    score: ScoreResult,
    threshold_decision: ThresholdDecision,
    trace_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Assemble a deterministic JSON-ready packet from existing run artifacts.

    The packet intentionally does not capture new data. Callers provide the run
    manifest reference, document versions, extracted-field provenance, correction
    history, score output, and threshold decision already produced by the intake
    pipeline.
    """

    return {
        "schema_version": "lineage-packet/v1",
        "run": {
            "run_id": run_id,
            "manifest_ref": manifest_ref,
            "trace_refs": sorted(trace_refs),
        },
        "documents": [_document_payload(document) for document in _sort_documents(documents)],
        "extracted_fields": _field_payloads(extracted_fields, correction_history),
        "threshold_decision": _threshold_payload(threshold_decision),
        "score": _score_payload(score),
    }


def _sort_documents(documents: Sequence[Document]) -> list[Document]:
    return sorted(documents, key=lambda document: document.document_id)


def _sort_fields(fields: Sequence[ExtractedFieldRecord]) -> list[ExtractedFieldRecord]:
    return sorted(fields, key=lambda field: (field.document_id, field.field_key, field.field_id))


def _sort_corrections(corrections: Sequence[CorrectionRecord]) -> list[CorrectionRecord]:
    return sorted(
        corrections, key=lambda correction: (correction.corrected_at, correction.correction_id)
    )


def _field_payloads(
    fields: Sequence[ExtractedFieldRecord],
    correction_history: Mapping[str, Sequence[CorrectionRecord]],
) -> list[dict[str, Any]]:
    corrections_by_field_id: dict[str, dict[int, CorrectionRecord]] = {}
    for corrections in correction_history.values():
        for correction in corrections:
            corrections_by_field_id.setdefault(correction.field_id, {})[
                correction.correction_id
            ] = correction

    return [
        _field_payload(
            field,
            tuple(corrections_by_field_id.get(field.field_id, {}).values()),
        )
        for field in _sort_fields(fields)
    ]


def _document_payload(document: Document) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "fund_id": document.fund_id,
        "file_name": document.file_name,
        "file_hash": document.file_hash,
        "received_at": document.received_at,
        "version_date": document.version_date,
        "source_channel": document.source_channel,
        "created_at": document.created_at,
    }


def _field_payload(
    field: ExtractedFieldRecord,
    corrections: Sequence[CorrectionRecord],
) -> dict[str, Any]:
    ordered_corrections = _sort_corrections(corrections)
    latest_value = ordered_corrections[-1].corrected_value if ordered_corrections else field.value
    return {
        "field_id": field.field_id,
        "document_id": field.document_id,
        "field_key": field.field_key,
        "original_value": field.value,
        "latest_value": latest_value,
        "confidence": field.confidence,
        "source_page": field.source_page,
        "source_snippet": field.source_snippet,
        "extracted_at": field.extracted_at,
        "corrections": [_correction_payload(correction) for correction in ordered_corrections],
    }


def _correction_payload(correction: CorrectionRecord) -> dict[str, Any]:
    return {
        "correction_id": correction.correction_id,
        "field_id": correction.field_id,
        "corrected_value": correction.corrected_value,
        "reason": correction.reason,
        "corrected_by": correction.corrected_by,
        "corrected_at": correction.corrected_at,
    }


def _threshold_payload(decision: ThresholdDecision) -> dict[str, Any]:
    return {
        "auto_accept_fields": sorted(decision.auto_accept_fields),
        "key_field_coverage_ratio": decision.key_field_coverage_ratio,
        "auto_pass_document": decision.auto_pass_document,
        "escalate": decision.escalate,
        "escalation_reason": decision.escalation_reason,
    }


def _score_payload(score: ScoreResult) -> dict[str, Any]:
    return {
        "manager_id": score.manager_id,
        "asset_class": score.asset_class,
        "base_score": score.base_score,
        "final_score": score.final_score,
        "contributions": {key: score.contributions[key] for key in sorted(score.contributions)},
        "red_flag_applied": score.red_flag_applied,
        "red_flag_reason": score.red_flag_reason,
        "peer_group_percentile": score.peer_group_percentile,
        "peer_group_size": score.peer_group_size,
    }
