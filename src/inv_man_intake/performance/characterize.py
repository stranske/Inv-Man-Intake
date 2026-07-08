"""Return-series standard-shape characterization and scoring gate."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from inv_man_intake.assist.egress_guard import (
    EgressConsent,
    LlmClient,
    ProviderConfig,
    send_to_llm,
)
from inv_man_intake.intake.standard_elements import StandardElementLibrary
from inv_man_intake.performance.contracts import PerformanceSeries, validate_series
from inv_man_intake.performance.metrics import PerformanceMetrics
from inv_man_intake.performance.normalize import detect_missing_months
from inv_man_intake.scoring.contracts import ScoreSubmission

CharacterizationTag = Literal[
    "standard",
    "pro_forma",
    "blended",
    "backfilled",
    "gross_net_ambiguous",
    "currency_noted",
    "composite",
]

_NON_STANDARD_TAGS: frozenset[CharacterizationTag] = frozenset(
    {
        "pro_forma",
        "blended",
        "backfilled",
        "gross_net_ambiguous",
        "currency_noted",
        "composite",
    }
)
_TAG_PRIORITY: tuple[CharacterizationTag, ...] = (
    "pro_forma",
    "blended",
    "backfilled",
    "gross_net_ambiguous",
    "currency_noted",
    "composite",
)
_KEYWORD_TAGS: tuple[tuple[CharacterizationTag, tuple[str, ...]], ...] = (
    ("pro_forma", ("pro forma", "pro-forma", "proforma")),
    ("blended", ("blended", "blend")),
    ("backfilled", ("backfilled", "backfill", "back-filled")),
    ("gross_net_ambiguous", ("gross vs net", "gross/net", "gross-vs-net", "gross net")),
    ("currency_noted", ("currency", "usd", "eur", "fx")),
    ("composite", ("composite",)),
)


@dataclass(frozen=True)
class SeriesCharacterization:
    """Typed characterization for one return series."""

    tag: CharacterizationTag
    rationale: str
    confidence: float
    metrics: PerformanceMetrics
    evidence: tuple[str, ...]
    doc_types_available: tuple[str, ...] = ()
    operator_confirmed: bool = False

    @property
    def requires_operator_confirmation(self) -> bool:
        """Whether the series must be confirmed before feeding scoring."""

        return self.tag in _NON_STANDARD_TAGS and not self.operator_confirmed


class _LlmCharacterizationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: CharacterizationTag
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("tag")
    @classmethod
    def _tag_must_not_standard(cls, value: CharacterizationTag) -> CharacterizationTag:
        if value == "standard":
            raise ValueError("LLM characterization is only used for ambiguous non-standard tails")
        return value


def characterize_series(
    series: PerformanceSeries,
    metrics: PerformanceMetrics,
    *,
    source_notes: Sequence[str] = (),
    source_names: Sequence[str] = (),
    standard_library: StandardElementLibrary | None = None,
    operator_confirmed: bool = False,
    consent: EgressConsent | None = None,
    provider_config: ProviderConfig | None = None,
    log_path: Path | None = None,
    client: LlmClient | None = None,
    now: Callable[[], datetime] | None = None,
) -> SeriesCharacterization:
    """Characterize return shape without mutating deterministic metric values."""

    validate_series(series)
    doc_types = standard_library.doc_types() if standard_library is not None else ()
    deterministic = _deterministic_characterization(
        series=series,
        metrics=metrics,
        source_notes=tuple(source_notes),
        source_names=tuple(source_names),
        doc_types=doc_types,
        operator_confirmed=operator_confirmed,
    )
    evidence = _evidence(source_notes=tuple(source_notes), source_names=tuple(source_names))
    if deterministic.tag != "standard" or not evidence:
        return deterministic
    if consent is None and provider_config is None and log_path is None and client is None:
        return deterministic
    if consent is None or provider_config is None or log_path is None or client is None:
        raise ValueError(
            "LLM characterization requires consent, provider_config, log_path, and client"
        )
    llm = _llm_characterization(
        source_notes=tuple(source_notes),
        source_names=tuple(source_names),
        consent=consent,
        provider_config=provider_config,
        log_path=log_path,
        client=client,
        now=now,
    )
    return SeriesCharacterization(
        tag=llm.tag,
        rationale=llm.rationale,
        confidence=llm.confidence,
        metrics=metrics,
        evidence=evidence,
        doc_types_available=doc_types,
        operator_confirmed=operator_confirmed,
    )


def require_operator_confirmation(
    characterization: SeriesCharacterization,
) -> SeriesCharacterization:
    """Return a confirmed characterization for explicit HITL scoring use."""

    return replace(characterization, operator_confirmed=True)


def gate_scoring_submission(
    submission: ScoreSubmission,
    *,
    characterization: SeriesCharacterization,
) -> ScoreSubmission:
    """Block non-standard return streams from scoring until confirmed."""

    if characterization.requires_operator_confirmation:
        raise PermissionError(
            "non-standard return series requires operator confirmation before scoring"
        )
    return submission


def _deterministic_characterization(
    *,
    series: PerformanceSeries,
    metrics: PerformanceMetrics,
    source_notes: tuple[str, ...],
    source_names: tuple[str, ...],
    doc_types: tuple[str, ...],
    operator_confirmed: bool,
) -> SeriesCharacterization:
    evidence = _evidence(source_notes=source_notes, source_names=source_names)
    matched_tags = _tags_from_text(evidence)
    missing_months = detect_missing_months(series) if series.frequency == "monthly" else ()
    if missing_months:
        matched_tags.append("backfilled")
        evidence = (*evidence, f"missing_months:{len(missing_months)}")
    tag = _highest_priority_tag(matched_tags)
    if tag is None:
        return SeriesCharacterization(
            tag="standard",
            rationale=_rationale_for_tag("standard"),
            confidence=0.92,
            metrics=metrics,
            evidence=evidence,
            doc_types_available=doc_types,
            operator_confirmed=operator_confirmed,
        )
    return SeriesCharacterization(
        tag=tag,
        rationale=_rationale_for_tag(tag),
        confidence=0.88,
        metrics=metrics,
        evidence=evidence,
        doc_types_available=doc_types,
        operator_confirmed=operator_confirmed,
    )


def _llm_characterization(
    *,
    source_notes: tuple[str, ...],
    source_names: tuple[str, ...],
    consent: EgressConsent,
    provider_config: ProviderConfig,
    log_path: Path,
    client: LlmClient,
    now: Callable[[], datetime] | None,
) -> _LlmCharacterizationPayload:
    guarded = send_to_llm(
        {
            "task": "classify ambiguous return-stream shape",
            "source_notes": source_notes,
            "source_names": source_names,
            "allowed_tags": _TAG_PRIORITY,
            "constraints": {
                "numbers_are_deterministic": True,
                "do_not_compute_or_change_returns": True,
            },
        },
        consent=consent,
        provider_config=provider_config,
        log_path=log_path,
        client=client,
        now=now,
    )
    try:
        return _LlmCharacterizationPayload.model_validate(guarded.provider_response)
    except ValidationError as exc:
        raise ValueError("invalid LLM characterization payload") from exc


def _evidence(*, source_notes: tuple[str, ...], source_names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item.strip() for item in (*source_notes, *source_names) if item.strip())


def _tags_from_text(evidence: tuple[str, ...]) -> list[CharacterizationTag]:
    haystack = " ".join(evidence).lower()
    return [
        tag
        for tag, needles in _KEYWORD_TAGS
        if any(_contains_keyword(haystack, needle) for needle in needles)
    ]


def _contains_keyword(haystack: str, needle: str) -> bool:
    return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None


def _highest_priority_tag(
    tags: Sequence[CharacterizationTag],
) -> CharacterizationTag | None:
    tag_set = set(tags)
    for tag in _TAG_PRIORITY:
        if tag in tag_set:
            return tag
    return None


def _rationale_for_tag(tag: CharacterizationTag) -> str:
    rationales: Mapping[CharacterizationTag, str] = {
        "standard": "No non-standard return-stream markers were detected.",
        "pro_forma": "Source evidence marks the stream as pro-forma.",
        "blended": "Source evidence indicates blended return data.",
        "backfilled": "Source evidence or month gaps indicate a backfilled stream.",
        "gross_net_ambiguous": "Source evidence leaves gross-versus-net treatment ambiguous.",
        "currency_noted": "Source evidence requires currency treatment review.",
        "composite": "Source evidence indicates composite return construction.",
    }
    return rationales[tag]
