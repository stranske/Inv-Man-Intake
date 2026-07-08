"""PPM standard/non-standard evaluator backed by the standard-element library."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inv_man_intake.assist.egress_guard import (
    EgressConsent,
    LlmClient,
    ProviderConfig,
    send_to_llm,
)
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.intake.standard_elements import ElementCoverage, StandardElementLibrary

_MAX_DEVIATION_DESCRIPTION_CHARS = 500


@dataclass(frozen=True)
class PpmChecklistItem:
    """One PPM standard-element coverage row."""

    key: str
    detected: bool
    mandatory: bool
    citation: str

    @property
    def status(self) -> str:
        """Compact operator-facing status."""

        if self.detected:
            return "present"
        if self.mandatory:
            return "missing"
        return "not observed"


@dataclass(frozen=True)
class DeviationNote:
    """Cited LLM description of an extracted non-standard PPM clause."""

    element_key: str
    summary: str
    why_it_matters: str
    citation: str
    apply_manually: bool = True


@dataclass(frozen=True)
class PpmEvaluation:
    """PPM coverage and deviation-note output for a single document."""

    document_id: str
    checklist: tuple[PpmChecklistItem, ...]
    deviation_notes: tuple[DeviationNote, ...]


def evaluate_ppm(
    extracted: ExtractedDocumentResult,
    library: StandardElementLibrary,
    *,
    consent: EgressConsent | None = None,
    provider_config: ProviderConfig | None = None,
    log_path: Path | None = None,
    client: LlmClient | None = None,
) -> PpmEvaluation:
    """Evaluate PPM element coverage and describe explicit deviation signals.

    Deterministic coverage never calls an LLM. Only extracted fields that already
    mark themselves as deviation candidates are sent through the egress guard.
    """

    coverage = library.evaluate_coverage("ppm", _coverage_payload(extracted))
    checklist = tuple(
        PpmChecklistItem(
            key=item.key,
            detected=item.detected,
            mandatory=item.mandatory,
            citation=_citation_for_coverage(item, extracted),
        )
        for item in coverage
    )
    candidates = _deviation_candidates(extracted)
    notes = (
        _describe_deviations(
            candidates,
            consent=consent,
            provider_config=provider_config,
            log_path=log_path,
            client=client,
        )
        if candidates
        else ()
    )
    return PpmEvaluation(
        document_id=extracted.source_doc_id,
        checklist=checklist,
        deviation_notes=notes,
    )


def _coverage_payload(extracted: ExtractedDocumentResult) -> dict[str, object]:
    return {
        "fields": {field.key for field in extracted.fields},
        "values": {field.key: field.value for field in extracted.fields},
    }


def _citation_for_coverage(
    coverage: ElementCoverage,
    extracted: ExtractedDocumentResult,
) -> str:
    field = _first_field(extracted, coverage.key)
    if field is None:
        return f"{extracted.source_doc_id}:{coverage.key}:missing"
    return _citation(field)


def _deviation_candidates(extracted: ExtractedDocumentResult) -> tuple[ExtractedField, ...]:
    return tuple(
        field
        for field in extracted.fields
        if field.key.startswith("ppm.deviation.") or "non-standard" in field.value.casefold()
    )


def _describe_deviations(
    candidates: tuple[ExtractedField, ...],
    *,
    consent: EgressConsent | None,
    provider_config: ProviderConfig | None,
    log_path: Path | None,
    client: LlmClient | None,
) -> tuple[DeviationNote, ...]:
    egress_config = (consent, provider_config, log_path, client)
    if all(item is None for item in egress_config):
        return ()
    if any(item is None for item in egress_config):
        raise ValueError(
            "PPM deviation notes require consent, provider_config, log_path, and client"
        )
    assert consent is not None
    assert provider_config is not None
    assert log_path is not None
    assert client is not None

    payload = {
        "task": "describe ppm deviation notes",
        "schema": {
            "notes": [
                {
                    "element_key": "string",
                    "summary": "string",
                    "why_it_matters": "string",
                    "citation": "string",
                }
            ]
        },
        "deviations": [
            {
                "element_key": field.key,
                "clause_description": field.value[:_MAX_DEVIATION_DESCRIPTION_CHARS],
                "citation": _citation(field),
            }
            for field in candidates
        ],
    }
    response = send_to_llm(
        payload,
        consent=consent,
        provider_config=provider_config,
        log_path=log_path,
        client=client,
    )
    return _parse_deviation_notes(response.provider_response, candidates)


def _parse_deviation_notes(
    response: Mapping[str, Any],
    candidates: tuple[ExtractedField, ...],
) -> tuple[DeviationNote, ...]:
    raw_notes = response.get("notes")
    if not isinstance(raw_notes, list):
        raise ValueError("PPM deviation response must contain a notes list")
    citations_by_key: dict[str, set[str]] = {}
    for field in candidates:
        citations_by_key.setdefault(field.key, set()).add(_citation(field))
    notes: list[DeviationNote] = []
    for raw_note in raw_notes:
        if not isinstance(raw_note, Mapping):
            raise ValueError("PPM deviation note must be an object")
        element_key = _required_response_string(raw_note, "element_key")
        citation = _required_response_string(raw_note, "citation")
        if element_key not in citations_by_key:
            raise ValueError(f"unknown PPM deviation element_key: {element_key}")
        if citation not in citations_by_key[element_key]:
            raise ValueError(f"uncited PPM deviation note: {element_key}")
        notes.append(
            DeviationNote(
                element_key=element_key,
                summary=_required_response_string(raw_note, "summary"),
                why_it_matters=_required_response_string(raw_note, "why_it_matters"),
                citation=citation,
            )
        )
    return tuple(notes)


def _required_response_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"PPM deviation note field {key!r} must be a non-empty string")
    return value


def _first_field(extracted: ExtractedDocumentResult, key: str) -> ExtractedField | None:
    return next((field for field in extracted.fields if field.key == key), None)


def _citation(field: ExtractedField) -> str:
    return f"{field.source_doc_id}:{field.key}:p{field.source_page}:{field.method}"
