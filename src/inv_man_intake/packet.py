"""Packet-level ingestion orchestration for multi-document manager profiles."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from inv_man_intake.extraction.cross_check import (
    CrossCheckReport,
    cross_check_extraction_results,
)
from inv_man_intake.extraction.doc_type import (
    DocumentType,
    classify_doc_type,
    contains_delimited_term,
)
from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractionProvider,
)
from inv_man_intake.intake.standard_elements import (
    ElementCoverage,
    StandardElementLibrary,
)


@dataclass(frozen=True)
class PacketFile:
    """One source document in a packet."""

    document_id: str
    content: bytes
    filename: str | None = None


@dataclass(frozen=True)
class PacketDocumentProfile:
    """Per-document extraction, routing, coverage, and lineage."""

    document_id: str
    filename: str | None
    document_type: str
    extraction: ExtractedDocumentResult
    standard_element_coverage: tuple[ElementCoverage, ...]
    lineage_refs: tuple[str, ...]


@dataclass(frozen=True)
class ManagerProfile:
    """Unified packet output consumed by the operator app and CLI."""

    packet_id: str
    documents: tuple[PacketDocumentProfile, ...]
    identity: Mapping[str, str]
    terms: Mapping[str, str]
    returns_metrics: Mapping[str, str]
    graphics_refs: tuple[str, ...]
    per_doc_standard_element_coverage: Mapping[str, tuple[ElementCoverage, ...]]
    flagged_non_standard_items: tuple[str, ...]
    scores: Mapping[str, float]
    lineage_refs: tuple[str, ...]
    reconciliation: CrossCheckReport

    @property
    def escalations(self) -> tuple[str, ...]:
        """Field-level reconciliation reasons that need analyst triage."""

        return self.reconciliation.escalation_reasons


def ingest_packet(
    files: Sequence[PacketFile],
    *,
    provider: ExtractionProvider,
    standard_library: StandardElementLibrary,
    packet_id: str = "packet",
    tolerance_percent: float = 5.0,
) -> ManagerProfile:
    """Extract a packet of documents and assemble one reconciled manager profile."""

    if not files:
        raise ValueError("packet must contain at least one file")
    _validate_unique_document_ids(files)

    document_profiles: list[PacketDocumentProfile] = []
    for packet_file in files:
        extraction = provider.extract(packet_file.document_id, packet_file.content)
        document_type = _classify_packet_document(
            packet_file=packet_file,
            extraction=extraction,
            standard_library=standard_library,
        )
        coverage = _evaluate_coverage(
            document_type=document_type,
            extraction=extraction,
            standard_library=standard_library,
        )
        document_profiles.append(
            PacketDocumentProfile(
                document_id=packet_file.document_id,
                filename=packet_file.filename,
                document_type=document_type,
                extraction=extraction,
                standard_element_coverage=coverage,
                lineage_refs=_lineage_refs(extraction),
            )
        )

    extractions = tuple(document.extraction for document in document_profiles)
    reconciliation = cross_check_extraction_results(
        extractions,
        tolerance_percent=tolerance_percent,
    )
    return ManagerProfile(
        packet_id=packet_id,
        documents=tuple(document_profiles),
        identity=MappingProxyType(_collect_fields(extractions, prefix="identity.")),
        terms=MappingProxyType(_collect_fields(extractions, prefix="terms.")),
        returns_metrics=MappingProxyType(_collect_fields(extractions, prefix="performance.")),
        graphics_refs=_graphics_refs(extractions),
        per_doc_standard_element_coverage=MappingProxyType(
            {
                document.document_id: document.standard_element_coverage
                for document in document_profiles
            }
        ),
        flagged_non_standard_items=_flagged_non_standard_items(document_profiles),
        scores=MappingProxyType(_scores(extractions)),
        lineage_refs=tuple(
            lineage_ref for document in document_profiles for lineage_ref in document.lineage_refs
        ),
        reconciliation=reconciliation,
    )


def _classify_packet_document(
    *,
    packet_file: PacketFile,
    extraction: ExtractedDocumentResult,
    standard_library: StandardElementLibrary,
) -> str:
    content = _classification_content(packet_file=packet_file, extraction=extraction)
    document_type = classify_doc_type(content, standard_library=standard_library)
    if document_type is DocumentType.UNKNOWN:
        return _library_doc_type_from_content(content, standard_library=standard_library)
    return document_type.value


def _classification_content(
    *,
    packet_file: PacketFile,
    extraction: ExtractedDocumentResult,
) -> tuple[str, ...]:
    content = packet_file.content.decode("utf-8", errors="ignore")
    field_values = tuple(str(field.value) for field in extraction.fields)
    filename = (packet_file.filename,) if packet_file.filename else ()
    return (content, *field_values, *filename)


def _library_doc_type_from_content(
    content: Sequence[str],
    *,
    standard_library: StandardElementLibrary,
) -> str:
    normalized = "\n".join(content).casefold()
    for doc_type in standard_library.doc_types():
        variants = {
            doc_type.casefold(),
            doc_type.casefold().replace("_", " "),
            doc_type.casefold().replace("_", "-"),
        }
        if any(contains_delimited_term(normalized, variant) for variant in variants):
            return doc_type
    return DocumentType.UNKNOWN.value


def _evaluate_coverage(
    *,
    document_type: str,
    extraction: ExtractedDocumentResult,
    standard_library: StandardElementLibrary,
) -> tuple[ElementCoverage, ...]:
    if document_type not in standard_library.doc_types():
        return ()
    extracted = {
        "fields": {field.key for field in extraction.fields},
        "values": {field.key: _coverage_value(field.value) for field in extraction.fields},
    }
    return standard_library.evaluate_coverage(document_type, extracted)


_NUMERIC_VALUE_RE = re.compile(
    r"^\s*[$€£]?\s*([+-]?(?:\d+(?:,\d{3})*|\d*)(?:\.\d+)?)\s*([%kmb])?\s*$",
    re.IGNORECASE,
)


def _coverage_value(value: str) -> str | float:
    match = _NUMERIC_VALUE_RE.match(value)
    if match is None:
        return value
    number_text = match.group(1)
    if not number_text or number_text in {"+", "-", "."}:
        return value
    numeric = float(number_text.replace(",", ""))
    suffix = (match.group(2) or "").casefold()
    multipliers = {"k": 1_000.0, "m": 1_000_000.0, "b": 1_000_000_000.0}
    if suffix in multipliers:
        numeric *= multipliers[suffix]
    return numeric


def _collect_fields(
    results: Sequence[ExtractedDocumentResult],
    *,
    prefix: str,
) -> dict[str, str]:
    collected: dict[str, str] = {}
    for result in results:
        for field in result.fields:
            if field.key.startswith(prefix):
                collected.setdefault(field.key, field.value)
    return collected


def _graphics_refs(results: Sequence[ExtractedDocumentResult]) -> tuple[str, ...]:
    refs: list[str] = []
    for result in results:
        images = getattr(result, "images", ())
        refs.extend(f"{result.source_doc_id}:image:{index}" for index, _ in enumerate(images))
    return tuple(refs)


def _flagged_non_standard_items(
    documents: Sequence[PacketDocumentProfile],
) -> tuple[str, ...]:
    flags: list[str] = []
    for document in documents:
        for coverage in document.standard_element_coverage:
            if coverage.mandatory and not coverage.detected:
                flags.append(f"{document.document_id}:{coverage.key}:missing_mandatory")
            if coverage.standardness != "unknown":
                flags.append(f"{document.document_id}:{coverage.key}:{coverage.standardness}")
    return tuple(flags)


def _scores(results: Sequence[ExtractedDocumentResult]) -> dict[str, float]:
    fields = [field for result in results for field in result.fields]
    if not fields:
        return {"extraction_confidence": 0.0}
    return {
        "extraction_confidence": sum(field.confidence for field in fields) / len(fields),
    }


def _lineage_refs(extraction: ExtractedDocumentResult) -> tuple[str, ...]:
    return tuple(
        f"{field.source_doc_id}:{field.key}:p{field.source_page}:{field.method}"
        for field in extraction.fields
    )


def _validate_unique_document_ids(files: Sequence[PacketFile]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for packet_file in files:
        if packet_file.document_id in seen:
            duplicates.add(packet_file.document_id)
        seen.add(packet_file.document_id)
    if duplicates:
        raise ValueError(
            "packet document_id values must be unique: " + ", ".join(sorted(duplicates))
        )
