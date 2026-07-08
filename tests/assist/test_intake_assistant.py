from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import inv_man_intake.assist.intake_assistant as assistant_module
from inv_man_intake.assist.egress_guard import EgressConsent, ProviderConfig
from inv_man_intake.assist.intake_assistant import answer_intake_question, collect_run_signals
from inv_man_intake.data.provenance import CorrectionRecord
from inv_man_intake.extraction.cross_check import CrossCheckReport, FieldCrossCheck
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.packet import ManagerProfile, PacketDocumentProfile
from inv_man_intake.scoring.contracts import ScoreResult


def test_recommendations_are_grounded_and_not_auto_applied(tmp_path: Path) -> None:
    outbound_calls: list[dict[str, Any]] = []

    def fake_client(
        payload: dict[str, Any],
        provider_config: ProviderConfig,
    ) -> Mapping[str, Any]:
        outbound_calls.append(payload)
        return {
            "answer": "The packet escalated because AUM disagreed across cited sources.",
            "citations": ["escalation:1"],
            "recommendations": [
                {
                    "rank": 1,
                    "change": "Tighten AUM parser review thresholds",
                    "rationale": "The AUM disagreement exceeded tolerance.",
                    "cited_evidence": ["escalation:1", "correction:7"],
                    "expected_effect": "Fewer silent AUM mismatches before analyst review.",
                }
            ],
        }

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    marker = config_dir / "thresholds.json"
    marker.write_text('{"aum": 0.05}\n', encoding="utf-8")

    answer = answer_intake_question(
        manager_profile=_manager_profile(),
        question="what should change?",
        corrections=(
            CorrectionRecord(
                correction_id=7,
                field_id="ppm-1:operations.aum",
                corrected_value="$105M",
                reason="analyst corrected AUM after source mismatch",
                corrected_by="operator",
                corrected_at="2026-07-07T09:00:00Z",
            ),
        ),
        score_result=ScoreResult(
            manager_id="manager-1",
            asset_class="credit",
            base_score=0.7,
            final_score=0.5,
            contributions={"operational_quality": 0.2},
            red_flag_applied=True,
            red_flag_reason="missing mandatory PPM fee disclosure",
        ),
        consent=EgressConsent(
            granted_by="operator",
            purpose="rank intake-improvement recommendations",
            granted_at="2026-07-07T09:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier-zero-retention",
            model="secure-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.jsonl",
        client=fake_client,
        now=lambda: datetime(2026, 7, 7, 9, 1, tzinfo=UTC),
    )

    assert answer.citations == ("escalation:1",)
    assert answer.recommendations[0].cited_evidence == ("escalation:1", "correction:7")
    assert answer.recommendations[0].apply_manually is True
    assert outbound_calls
    assert outbound_calls[0]["constraints"] == {
        "recommend_only": True,
        "must_cite_signal_ids": True,
        "no_config_writes": True,
    }
    assert marker.read_text(encoding="utf-8") == '{"aum": 0.05}\n'


def test_assistant_normalizes_citation_whitespace(tmp_path: Path) -> None:
    def fake_client(
        payload: dict[str, Any],
        provider_config: ProviderConfig,
    ) -> Mapping[str, Any]:
        return {
            "answer": "The packet escalated because sources disagree.",
            "citations": [" escalation:1 "],
            "recommendations": [
                {
                    "change": "Review source reconciliation",
                    "rationale": "The escalation is grounded in cross-document evidence.",
                    "cited_evidence": [" escalation:1 "],
                    "expected_effect": "Keeps recommendations tied to known packet signals.",
                }
            ],
        }

    answer = answer_intake_question(
        manager_profile=_manager_profile(),
        question="what should change?",
        consent=EgressConsent(
            granted_by="operator",
            purpose="rank intake-improvement recommendations",
            granted_at="2026-07-07T09:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier-zero-retention",
            model="secure-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.jsonl",
        client=fake_client,
    )

    assert answer.citations == ("escalation:1",)
    assert answer.recommendations[0].cited_evidence == ("escalation:1",)


def test_assistant_rejects_uncited_recommendations(tmp_path: Path) -> None:
    def fake_client(
        payload: dict[str, Any],
        provider_config: ProviderConfig,
    ) -> Mapping[str, Any]:
        return {
            "answer": "Make a change.",
            "citations": ["escalation:1"],
            "recommendations": [
                {
                    "change": "Change parser",
                    "rationale": "No citation is available.",
                    "cited_evidence": ["made-up-signal"],
                    "expected_effect": "Unknown",
                }
            ],
        }

    with pytest.raises(ValueError, match="not backed by a run signal"):
        answer_intake_question(
            manager_profile=_manager_profile(),
            question="what should change?",
            consent=EgressConsent(
                granted_by="operator",
                purpose="rank intake-improvement recommendations",
                granted_at="2026-07-07T09:00:00Z",
            ),
            provider_config=ProviderConfig(
                provider="frontier-zero-retention",
                model="secure-model",
                zero_retention=True,
                baa_eligible=True,
            ),
            log_path=tmp_path / "egress.jsonl",
            client=fake_client,
        )


def test_assistant_rejects_uncited_answers(tmp_path: Path) -> None:
    def fake_client(
        payload: dict[str, Any],
        provider_config: ProviderConfig,
    ) -> Mapping[str, Any]:
        return {"answer": "No evidence cited.", "citations": [], "recommendations": []}

    with pytest.raises(ValueError, match="citations"):
        answer_intake_question(
            manager_profile=_manager_profile(),
            question="what should change?",
            consent=EgressConsent(
                granted_by="operator",
                purpose="rank intake-improvement recommendations",
                granted_at="2026-07-07T09:00:00Z",
            ),
            provider_config=ProviderConfig(
                provider="frontier-zero-retention",
                model="secure-model",
                zero_retention=True,
                baa_eligible=True,
            ),
            log_path=tmp_path / "egress.jsonl",
            client=fake_client,
        )


def test_standardness_signal_ids_are_category_stable() -> None:
    profile = _manager_profile()

    signals = collect_run_signals(manager_profile=profile)

    assert [signal.signal_id for signal in signals if signal.category == "standardness"] == [
        "standardness:1"
    ]


def test_assistant_routes_through_egress_guard(tmp_path: Path) -> None:
    def fake_client(
        payload: dict[str, Any],
        provider_config: ProviderConfig,
    ) -> Mapping[str, Any]:
        return {"answer": "grounded", "citations": ["escalation:1"], "recommendations": []}

    answer_intake_question(
        manager_profile=_manager_profile(),
        question="what changed?",
        consent=EgressConsent(
            granted_by="operator",
            purpose="rank intake-improvement recommendations",
            granted_at="2026-07-07T09:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier-zero-retention",
            model="secure-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.jsonl",
        client=fake_client,
    )

    log_record = json.loads((tmp_path / "egress.jsonl").read_text(encoding="utf-8"))
    assert log_record["purpose"] == "rank intake-improvement recommendations"


def test_direct_provider_call_rejected_without_egress_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard_calls = 0

    def fake_guard(*args: object, **kwargs: object) -> object:
        nonlocal guard_calls
        guard_calls += 1
        raise AssertionError("direct provider path must not call egress guard")

    def direct_provider(
        payload: dict[str, Any],
        provider_config: ProviderConfig,
    ) -> Mapping[str, Any]:
        raise PermissionError("provider calls must cross egress_guard.send_to_llm")

    monkeypatch.setattr(assistant_module, "send_to_llm", fake_guard)

    with pytest.raises(PermissionError, match="egress_guard.send_to_llm"):
        direct_provider(
            {"question": "what should change?"},
            ProviderConfig(
                provider="frontier-zero-retention",
                model="secure-model",
                zero_retention=True,
                baa_eligible=True,
            ),
        )

    assert guard_calls == 0


def test_assistant_flows_do_not_mutate_config_directory(tmp_path: Path) -> None:
    def fake_client(
        payload: dict[str, Any],
        provider_config: ProviderConfig,
    ) -> Mapping[str, Any]:
        return {
            "answer": "The packet escalated because sources disagree.",
            "citations": ["escalation:1"],
            "recommendations": [
                {
                    "change": "Review source reconciliation",
                    "rationale": "The escalation is grounded in cross-document evidence.",
                    "cited_evidence": ["escalation:1"],
                    "expected_effect": "Keeps recommendations tied to known packet signals.",
                }
            ],
        }

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "thresholds.json"
    config_file.write_text('{"aum": 0.05}\n', encoding="utf-8")
    before = _snapshot_tree(config_dir)

    answer_intake_question(
        manager_profile=_manager_profile(),
        question="what should change?",
        consent=EgressConsent(
            granted_by="operator",
            purpose="rank intake-improvement recommendations",
            granted_at="2026-07-07T09:00:00Z",
        ),
        provider_config=ProviderConfig(
            provider="frontier-zero-retention",
            model="secure-model",
            zero_retention=True,
            baa_eligible=True,
        ),
        log_path=tmp_path / "egress.jsonl",
        client=fake_client,
    )

    assert _snapshot_tree(config_dir) == before


def _snapshot_tree(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _manager_profile() -> ManagerProfile:
    extraction = ExtractedDocumentResult(
        source_doc_id="ppm-1",
        provider_name="stub",
        fields=(
            ExtractedField(
                key="operations.aum",
                value="$100M",
                confidence=0.64,
                source_doc_id="ppm-1",
                source_page=3,
                snippet="AUM $100M",
                method="text",
            ),
        ),
    )
    document = PacketDocumentProfile(
        document_id="ppm-1",
        filename="ppm.pdf",
        document_type="ppm",
        extraction=extraction,
        standard_element_coverage=(),
        lineage_refs=("ppm-1:operations.aum:p3:text",),
    )
    return ManagerProfile(
        packet_id="packet-1",
        documents=(document,),
        identity={},
        terms={},
        returns_metrics={},
        graphics_refs=(),
        per_doc_standard_element_coverage={},
        flagged_non_standard_items=("ppm-1:fees:missing_mandatory",),
        scores={"extraction_confidence": 0.64},
        lineage_refs=("ppm-1:operations.aum:p3:text",),
        reconciliation=CrossCheckReport(
            fields=(
                FieldCrossCheck(
                    key="operations.aum",
                    observations=(),
                    accepted_value="$100M",
                    accepted_source="stub:text:ppm-1:p3",
                    escalate=True,
                    reason="cross_check_disagreement:operations.aum:ppm-1!=deck-1",
                ),
            ),
        ),
    )
