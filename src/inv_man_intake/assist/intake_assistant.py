"""Grounded intake-improvement assistant over packet/run signals."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inv_man_intake.assist.egress_guard import (
    EgressConsent,
    LlmClient,
    ProviderConfig,
    send_to_llm,
)
from inv_man_intake.data.provenance import CorrectionRecord
from inv_man_intake.packet import ManagerProfile
from inv_man_intake.scoring.contracts import ScoreResult


@dataclass(frozen=True)
class RunSignal:
    """One cited signal available to the assistant."""

    signal_id: str
    category: str
    summary: str
    source_ref: str
    severity: float


@dataclass(frozen=True)
class IntakeRecommendation:
    """Operator-facing recommendation that must remain human-applied."""

    change: str
    rationale: str
    cited_evidence: tuple[str, ...]
    expected_effect: str
    rank: int
    apply_manually: bool = True


@dataclass(frozen=True)
class AssistantAnswer:
    """Grounded assistant response for one operator question."""

    answer: str
    citations: tuple[str, ...]
    recommendations: tuple[IntakeRecommendation, ...]


class _RecommendationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    cited_evidence: tuple[str, ...] = Field(min_length=1)
    expected_effect: str = Field(min_length=1)
    rank: int | None = Field(default=None, ge=1)

    @field_validator("cited_evidence")
    @classmethod
    def _citations_must_be_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not citation.strip() for citation in value):
            raise ValueError("citations must be non-empty strings")
        return value


class _AssistantResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    citations: tuple[str, ...]
    recommendations: tuple[_RecommendationPayload, ...]

    @field_validator("citations")
    @classmethod
    def _citations_must_be_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not citation.strip() for citation in value):
            raise ValueError("citations must be non-empty strings")
        return value


def answer_intake_question(
    *,
    manager_profile: ManagerProfile,
    question: str,
    consent: EgressConsent,
    provider_config: ProviderConfig,
    log_path: Path,
    client: LlmClient,
    corrections: Sequence[CorrectionRecord] = (),
    score_result: ScoreResult | None = None,
    now: Callable[[], Any] | None = None,
) -> AssistantAnswer:
    """Return cited, recommend-only guidance through the egress guard."""

    signals = collect_run_signals(
        manager_profile=manager_profile,
        corrections=corrections,
        score_result=score_result,
    )
    signal_by_id = {signal.signal_id: signal for signal in signals}
    payload = {
        "task": "rank intake-improvement recommendations",
        "question": question,
        "packet_id": manager_profile.packet_id,
        "signals": [
            {
                "id": signal.signal_id,
                "category": signal.category,
                "summary": signal.summary,
                "source_ref": signal.source_ref,
                "severity": signal.severity,
            }
            for signal in signals
        ],
        "constraints": {
            "recommend_only": True,
            "must_cite_signal_ids": True,
            "no_config_writes": True,
        },
    }
    guarded = send_to_llm(
        payload,
        consent=consent,
        provider_config=provider_config,
        log_path=log_path,
        client=client,
        now=now,
    )
    return _validate_assistant_response(guarded.provider_response, signal_by_id=signal_by_id)


def collect_run_signals(
    *,
    manager_profile: ManagerProfile,
    corrections: Sequence[CorrectionRecord] = (),
    score_result: ScoreResult | None = None,
) -> tuple[RunSignal, ...]:
    """Flatten packet, provenance, and score signals into citeable inputs."""

    signals: list[RunSignal] = []
    for index, reason in enumerate(manager_profile.escalations, start=1):
        signals.append(
            RunSignal(
                signal_id=f"escalation:{index}",
                category="escalation",
                summary=reason,
                source_ref=(
                    manager_profile.lineage_refs[0]
                    if manager_profile.lineage_refs
                    else manager_profile.packet_id
                ),
                severity=0.95,
            )
        )
    for flag in manager_profile.flagged_non_standard_items:
        document_id, _, _ = flag.partition(":")
        signals.append(
            RunSignal(
                signal_id=f"standardness:{len(signals) + 1}",
                category="standardness",
                summary=flag,
                source_ref=document_id or manager_profile.packet_id,
                severity=0.80,
            )
        )
    for correction in corrections:
        signals.append(
            RunSignal(
                signal_id=f"correction:{correction.correction_id}",
                category="correction",
                summary=correction.reason or f"corrected {correction.field_id}",
                source_ref=correction.field_id,
                severity=0.70,
            )
        )
    if score_result and score_result.red_flag_reason:
        signals.append(
            RunSignal(
                signal_id="score:red_flag",
                category="score",
                summary=score_result.red_flag_reason,
                source_ref=score_result.manager_id,
                severity=0.90,
            )
        )
    return tuple(signals)


def _validate_assistant_response(
    response: Mapping[str, Any],
    *,
    signal_by_id: Mapping[str, RunSignal],
) -> AssistantAnswer:
    parsed = _AssistantResponsePayload.model_validate(response)
    if not parsed.citations and parsed.recommendations:
        raise ValueError("assistant response must cite evidence")

    recommendations = tuple(
        _recommendation_from_payload(index=index, payload=payload, signal_by_id=signal_by_id)
        for index, payload in enumerate(parsed.recommendations, start=1)
    )
    for citation in parsed.citations:
        if citation not in signal_by_id:
            raise ValueError(f"assistant citation is not backed by a run signal: {citation}")
    return AssistantAnswer(
        answer=parsed.answer,
        citations=parsed.citations,
        recommendations=recommendations,
    )


def _recommendation_from_payload(
    *,
    index: int,
    payload: _RecommendationPayload,
    signal_by_id: Mapping[str, RunSignal],
) -> IntakeRecommendation:
    for citation in payload.cited_evidence:
        if citation not in signal_by_id:
            raise ValueError(f"recommendation citation is not backed by a run signal: {citation}")
    return IntakeRecommendation(
        change=payload.change,
        rationale=payload.rationale,
        cited_evidence=payload.cited_evidence,
        expected_effect=payload.expected_effect,
        rank=payload.rank or index,
        apply_manually=True,
    )
