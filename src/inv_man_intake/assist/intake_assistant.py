"""Grounded intake-improvement assistant over packet/run signals."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
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

_ESCALATION_SEVERITY = 0.95
_STANDARDNESS_SEVERITY = 0.80
_CORRECTION_SEVERITY = 0.70
_SCORE_RED_FLAG_SEVERITY = 0.90


@dataclass(frozen=True)
class RunSignal:
    """One citable signal available to the assistant."""

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


@dataclass(frozen=True)
class AssistantSessionState:
    """Run-signal-backed assistant context shared by recommendations and follow-ups."""

    session_id: str
    question: str
    signals: tuple[RunSignal, ...]
    answer: AssistantAnswer


def build_assistant_session(
    *,
    packet_id: str,
    question: str,
    signals: Sequence[RunSignal],
) -> AssistantSessionState:
    """Build deterministic recommend-only assistant state from current run signals."""

    signal_tuple = tuple(signals)
    ranked_signals = tuple(
        sorted(signal_tuple, key=lambda signal: (-signal.severity, signal.signal_id))
    )
    recommendations = tuple(
        IntakeRecommendation(
            rank=index,
            change=_recommendation_change(signal),
            rationale=f"Grounded in {signal.category} signal: {signal.summary}",
            cited_evidence=(signal.signal_id,),
            expected_effect="Keeps the operator review tied to current packet evidence.",
        )
        for index, signal in enumerate(ranked_signals[:3], start=1)
    )
    citations = tuple(signal.signal_id for signal in ranked_signals[:1])
    answer = AssistantAnswer(
        answer=(
            f"Review {ranked_signals[0].category} evidence before changing intake behavior."
            if ranked_signals
            else "No current run signals require an assistant recommendation."
        ),
        citations=citations,
        recommendations=recommendations,
    )
    return AssistantSessionState(
        session_id=f"{packet_id}:assistant:{len(signal_tuple)}",
        question=question,
        signals=signal_tuple,
        answer=answer,
    )


def answer_followup_from_state(*, state: AssistantSessionState, question: str) -> AssistantAnswer:
    """Answer a follow-up question using the existing assistant session context."""

    ranked_signals = tuple(
        sorted(state.signals, key=lambda signal: (-signal.severity, signal.signal_id))
    )
    if not ranked_signals:
        return AssistantAnswer(
            answer=f"No run-signal context is available for follow-up: {question}",
            citations=(),
            recommendations=(),
        )
    primary = ranked_signals[0]
    return AssistantAnswer(
        answer=(
            f"Using session {state.session_id}, the strongest signal remains "
            f"{primary.signal_id}: {primary.summary}"
        ),
        citations=(primary.signal_id,),
        recommendations=state.answer.recommendations,
    )


def _require_non_empty_citations(value: tuple[str, ...]) -> tuple[str, ...]:
    stripped = tuple(citation.strip() for citation in value)
    if any(not citation for citation in stripped):
        raise ValueError("citations must be non-empty strings")
    return stripped


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
        return _require_non_empty_citations(value)


class _AssistantResponsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1)
    citations: tuple[str, ...] = Field(min_length=1)
    recommendations: tuple[_RecommendationPayload, ...]

    @field_validator("citations")
    @classmethod
    def _citations_must_be_non_empty(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_non_empty_citations(value)


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
    now: Callable[[], datetime] | None = None,
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
    """Flatten packet, provenance, and score signals into citable inputs."""

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
                severity=_ESCALATION_SEVERITY,
            )
        )
    for index, flag in enumerate(manager_profile.flagged_non_standard_items, start=1):
        document_id, _, _ = flag.partition(":")
        signals.append(
            RunSignal(
                signal_id=f"standardness:{index}",
                category="standardness",
                summary=flag,
                source_ref=document_id or manager_profile.packet_id,
                severity=_STANDARDNESS_SEVERITY,
            )
        )
    for correction in corrections:
        signals.append(
            RunSignal(
                signal_id=f"correction:{correction.correction_id}",
                category="correction",
                summary=correction.reason or f"corrected {correction.field_id}",
                source_ref=correction.field_id,
                severity=_CORRECTION_SEVERITY,
            )
        )
    if score_result and score_result.red_flag_reason:
        signals.append(
            RunSignal(
                signal_id="score:red_flag",
                category="score",
                summary=score_result.red_flag_reason,
                source_ref=score_result.manager_id,
                severity=_SCORE_RED_FLAG_SEVERITY,
            )
        )
    return tuple(signals)


def _validate_assistant_response(
    response: Mapping[str, Any],
    *,
    signal_by_id: Mapping[str, RunSignal],
) -> AssistantAnswer:
    parsed = _AssistantResponsePayload.model_validate(response)
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


def _recommendation_change(signal: RunSignal) -> str:
    if signal.category == "escalation":
        return "Review the escalated packet evidence"
    if signal.category == "standardness":
        return "Check non-standard document coverage"
    if signal.category == "score":
        return "Confirm score red-flag handling"
    if signal.category == "correction":
        return "Reconcile corrected source values"
    return "Review current intake signal"
