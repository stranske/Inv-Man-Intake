"""Tests for regulatory lineage packet assembly."""

from __future__ import annotations

import json

from inv_man_intake.audit.lineage import build_lineage_packet
from inv_man_intake.data.models import Document
from inv_man_intake.data.provenance import CorrectionRecord, ExtractedFieldRecord
from inv_man_intake.extraction.confidence import ThresholdDecision
from inv_man_intake.scoring.contracts import ScoreResult


def test_lineage_packet_contains_required_sections() -> None:
    document = Document(
        document_id="doc_1",
        fund_id="fund_1",
        file_name="alpha_ppm.pdf",
        file_hash="sha256:abc123",
        received_at="2026-03-01T09:00:00Z",
        version_date="2026-03-01",
        source_channel="email",
        created_at="2026-03-01T09:00:00Z",
    )
    field = ExtractedFieldRecord(
        field_id="field_1",
        document_id="doc_1",
        field_key="terms.management_fee",
        value="2.00%",
        confidence=0.82,
        source_page=4,
        source_snippet="Management fee: 2.00%",
        extracted_at="2026-03-01T09:05:00Z",
    )
    correction = CorrectionRecord(
        correction_id=1,
        field_id="field_1",
        corrected_value="1.85%",
        reason="Analyst corrected against final PPM",
        corrected_by="analyst@example.com",
        corrected_at="2026-03-01T10:00:00Z",
    )
    score = ScoreResult(
        manager_id="mgr_1",
        asset_class="equity_market_neutral",
        base_score=0.72,
        final_score=0.68,
        contributions={"terms": 0.20, "performance": 0.52},
        red_flag_applied=True,
        red_flag_reason="threshold_escalation",
        peer_group_percentile=62.5,
        peer_group_size=40,
    )
    decision = ThresholdDecision(
        auto_accept_fields=("performance.net_return_1y",),
        key_field_coverage_ratio=0.75,
        auto_pass_document=False,
        escalate=True,
        escalation_reason="confidence_below_threshold:terms.management_fee",
    )

    packet = build_lineage_packet(
        run_id="run_123",
        manifest_ref="artifact:manifest.json",
        documents=(document,),
        extracted_fields=(field,),
        correction_history={"field_1": (correction,)},
        score=score,
        threshold_decision=decision,
        trace_refs=("trace:abc",),
    )
    packet_again = build_lineage_packet(
        run_id="run_123",
        manifest_ref="artifact:manifest.json",
        documents=(document,),
        extracted_fields=(field,),
        correction_history={"field_1": (correction,)},
        score=score,
        threshold_decision=decision,
        trace_refs=("trace:abc",),
    )

    assert packet["run"]["run_id"] == "run_123"
    assert packet["run"]["manifest_ref"] == "artifact:manifest.json"
    assert packet["documents"] == [
        {
            "document_id": "doc_1",
            "fund_id": "fund_1",
            "file_name": "alpha_ppm.pdf",
            "file_hash": "sha256:abc123",
            "received_at": "2026-03-01T09:00:00Z",
            "version_date": "2026-03-01",
            "source_channel": "email",
            "created_at": "2026-03-01T09:00:00Z",
        }
    ]
    assert packet["extracted_fields"][0]["field_key"] == "terms.management_fee"
    assert packet["extracted_fields"][0]["confidence"] == 0.82
    assert packet["extracted_fields"][0]["latest_value"] == "1.85%"
    assert packet["extracted_fields"][0]["corrections"][0]["reason"] == (
        "Analyst corrected against final PPM"
    )
    assert packet["threshold_decision"] == {
        "auto_accept_fields": ["performance.net_return_1y"],
        "key_field_coverage_ratio": 0.75,
        "auto_pass_document": False,
        "escalate": True,
        "escalation_reason": "confidence_below_threshold:terms.management_fee",
    }
    assert packet["score"] == {
        "manager_id": "mgr_1",
        "asset_class": "equity_market_neutral",
        "base_score": 0.72,
        "final_score": 0.68,
        "contributions": {"performance": 0.52, "terms": 0.20},
        "red_flag_applied": True,
        "red_flag_reason": "threshold_escalation",
        "peer_group_percentile": 62.5,
        "peer_group_size": 40,
    }
    assert json.dumps(packet, sort_keys=True) == json.dumps(packet_again, sort_keys=True)


def test_lineage_packet_matches_corrections_by_field_id_not_history_key() -> None:
    document = _document()
    field = _field(field_id="field_1", value="2.00%")
    duplicate_correction = CorrectionRecord(
        correction_id=1,
        field_id="field_1",
        corrected_value="1.90%",
        reason="First analyst correction",
        corrected_by="analyst@example.com",
        corrected_at="2026-03-01T10:00:00Z",
    )
    latest_correction = CorrectionRecord(
        correction_id=2,
        field_id="field_1",
        corrected_value="1.85%",
        reason="Final analyst correction",
        corrected_by="analyst@example.com",
        corrected_at="2026-03-01T10:05:00Z",
    )

    packet = build_lineage_packet(
        run_id="run_123",
        manifest_ref="artifact:manifest.json",
        documents=(document,),
        extracted_fields=(field,),
        correction_history={
            "legacy-source-key": (duplicate_correction, latest_correction),
            "field_1": (duplicate_correction,),
        },
        score=_score(),
        threshold_decision=_decision(),
    )

    field_payload = packet["extracted_fields"][0]
    assert field_payload["latest_value"] == "1.85%"
    assert [correction["correction_id"] for correction in field_payload["corrections"]] == [1, 2]


def test_lineage_packet_preserves_original_value_without_corrections() -> None:
    packet = build_lineage_packet(
        run_id="run_123",
        manifest_ref="artifact:manifest.json",
        documents=(_document(),),
        extracted_fields=(_field(field_id="field_without_correction", value="2.00%"),),
        correction_history={},
        score=_score(),
        threshold_decision=_decision(),
    )

    field_payload = packet["extracted_fields"][0]
    assert field_payload["latest_value"] == "2.00%"
    assert field_payload["corrections"] == []


def _document() -> Document:
    return Document(
        document_id="doc_1",
        fund_id="fund_1",
        file_name="alpha_ppm.pdf",
        file_hash="sha256:abc123",
        received_at="2026-03-01T09:00:00Z",
        version_date="2026-03-01",
        source_channel="email",
        created_at="2026-03-01T09:00:00Z",
    )


def _field(*, field_id: str, value: str) -> ExtractedFieldRecord:
    return ExtractedFieldRecord(
        field_id=field_id,
        document_id="doc_1",
        field_key="terms.management_fee",
        value=value,
        confidence=0.82,
        source_page=4,
        source_snippet="Management fee: 2.00%",
        extracted_at="2026-03-01T09:05:00Z",
    )


def _score() -> ScoreResult:
    return ScoreResult(
        manager_id="mgr_1",
        asset_class="equity_market_neutral",
        base_score=0.72,
        final_score=0.68,
        contributions={"terms": 0.20, "performance": 0.52},
        red_flag_applied=True,
        red_flag_reason="threshold_escalation",
        peer_group_percentile=62.5,
        peer_group_size=40,
    )


def _decision() -> ThresholdDecision:
    return ThresholdDecision(
        auto_accept_fields=("performance.net_return_1y",),
        key_field_coverage_ratio=0.75,
        auto_pass_document=False,
        escalate=True,
        escalation_reason="confidence_below_threshold:terms.management_fee",
    )
