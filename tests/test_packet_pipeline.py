"""Tests for packet-level manager profile assembly."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import inv_man_intake.packet
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.intake.standard_elements import load_standard_element_library
from inv_man_intake.packet import PacketFile, ingest_packet


def test_multi_doc_packet_assembles_profile_and_reconciles() -> None:
    library = load_standard_element_library(
        {
            "version": "packet-test",
            "non_authoritative": True,
            "doc_types": {
                "deck": [
                    {
                        "key": "operations.aum",
                        "detector_name": "field_present",
                        "mandatory": True,
                    }
                ],
                "track_record": [
                    {
                        "key": "performance.net_return_1y",
                        "detector_name": "field_present",
                        "mandatory": True,
                    }
                ],
            },
        }
    )
    provider = _PacketProvider(
        {
            "deck": _result(
                source_doc_id="deck",
                provider_name="deck-provider",
                fields=(
                    _field("operations.aum", "$100.0M", "deck-regex", 0.91),
                    _field("terms.management_fee", "1.25%", "deck-regex", 0.88),
                ),
            ),
            "track": _result(
                source_doc_id="track",
                provider_name="track-provider",
                fields=(
                    _field("operations.aum", "$89.0M", "track-regex", 0.89),
                    _field("performance.net_return_1y", "12.5%", "track-regex", 0.87),
                ),
            ),
        }
    )

    profile = ingest_packet(
        (
            PacketFile(document_id="deck", content=b"deck packet", filename="deck.txt"),
            PacketFile(
                document_id="track",
                content=b"track_record packet",
                filename="track-record.txt",
            ),
        ),
        provider=provider,
        standard_library=library,
        packet_id="manager-packet",
    )

    assert profile.packet_id == "manager-packet"
    assert {document.document_id for document in profile.documents} == {"deck", "track"}
    assert profile.terms["terms.management_fee"] == "1.25%"
    assert profile.returns_metrics["performance.net_return_1y"] == "12.5%"
    assert profile.per_doc_standard_element_coverage["deck"][0].detected is True
    assert profile.per_doc_standard_element_coverage["track"][0].detected is True
    assert profile.escalations
    assert profile.escalations[0].startswith("cross_check_disagreement:operations.aum")
    assert profile.lineage_refs
    assert profile.scores["extraction_confidence"] > 0


def test_packet_rejects_duplicate_document_ids() -> None:
    provider = _PacketProvider(
        {
            "duplicate": _result(
                source_doc_id="duplicate",
                provider_name="provider",
                fields=(),
            )
        }
    )

    try:
        ingest_packet(
            (
                PacketFile(document_id="duplicate", content=b"left"),
                PacketFile(document_id="duplicate", content=b"right"),
            ),
            provider=provider,
            standard_library=_library_for_doc_type("duplicate"),
        )
    except ValueError as exc:
        assert "document_id values must be unique" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("duplicate document ids should fail fast")


def test_manager_profile_mappings_are_read_only() -> None:
    profile = ingest_packet(
        (PacketFile(document_id="deck", content=b"deck"),),
        provider=_PacketProvider(
            {
                "deck": _result(
                    source_doc_id="deck",
                    provider_name="deck-provider",
                    fields=(_field("identity.manager", "Alpha", "deck", 0.9),),
                )
            }
        ),
        standard_library=_library_for_doc_type("deck"),
    )

    for mapping in (
        profile.identity,
        profile.terms,
        profile.returns_metrics,
        profile.per_doc_standard_element_coverage,
        profile.scores,
    ):
        assert type(mapping).__name__ == "mappingproxy"


def test_multi_doc_packet_fails_without_reconciliation() -> None:
    profile = ingest_packet(
        (
            PacketFile(document_id="left", content=b"left"),
            PacketFile(document_id="right", content=b"right"),
        ),
        provider=_PacketProvider(
            {
                "left": _result(
                    source_doc_id="left",
                    provider_name="left-provider",
                    fields=(_field("operations.aum", "$100M", "left", 0.9),),
                ),
                "right": _result(
                    source_doc_id="right",
                    provider_name="right-provider",
                    fields=(_field("operations.aum", "$80M", "right", 0.8),),
                ),
            }
        ),
        standard_library=load_standard_element_library(
            {
                "version": "packet-test",
                "non_authoritative": True,
                "doc_types": {
                    "left": [
                        {
                            "key": "operations.aum",
                            "detector_name": "field_present",
                            "mandatory": True,
                        }
                    ]
                },
            },
        ),
    )

    assert profile.escalations, "disabling cross-document reconciliation must fail this gate"


def test_packet_routes_throwaway_doc_type_through_library_data() -> None:
    throwaway_doc_type = "library_added_packet_type"
    library = load_standard_element_library(
        {
            "version": "packet-test",
            "non_authoritative": True,
            "doc_types": {
                throwaway_doc_type: [
                    {
                        "key": "custom.metric",
                        "detector_name": "field_present",
                        "mandatory": False,
                    }
                ]
            },
        }
    )

    profile = ingest_packet(
        (PacketFile(document_id="custom", content=throwaway_doc_type.encode()),),
        provider=_PacketProvider(
            {
                "custom": _result(
                    source_doc_id="custom",
                    provider_name="custom-provider",
                    fields=(_field("custom.metric", "present", "custom", 0.8),),
                )
            }
        ),
        standard_library=library,
    )

    assert profile.documents[0].document_type == throwaway_doc_type
    assert profile.per_doc_standard_element_coverage["custom"][0].detected is True
    packet_source = Path(inv_man_intake.packet.__file__).read_text()
    assert throwaway_doc_type not in packet_source
    assert "custom.metric" not in packet_source


def test_packet_library_doc_type_fallback_is_delimiter_aware() -> None:
    library = load_standard_element_library(
        {
            "version": "packet-test",
            "non_authoritative": True,
            "doc_types": {
                "deck": [
                    {
                        "key": "operations.aum",
                        "detector_name": "field_present",
                        "mandatory": True,
                    }
                ]
            },
        }
    )

    profile = ingest_packet(
        (PacketFile(document_id="feedback", content=b"customer feedback"),),
        provider=_PacketProvider(
            {
                "feedback": _result(
                    source_doc_id="feedback",
                    provider_name="feedback-provider",
                    fields=(_field("operations.aum", "$100M", "feedback", 0.8),),
                )
            }
        ),
        standard_library=library,
    )

    assert profile.documents[0].document_type == "unknown"
    assert profile.per_doc_standard_element_coverage["feedback"] == ()


def test_packet_numeric_detector_uses_field_values_payload() -> None:
    library = load_standard_element_library(
        {
            "version": "packet-test",
            "non_authoritative": True,
            "doc_types": {
                "deck": [
                    {
                        "key": "operations.aum",
                        "detector_name": "numeric_field_present",
                        "mandatory": True,
                    }
                ]
            },
        }
    )

    profile = ingest_packet(
        (PacketFile(document_id="deck", content=b"deck"),),
        provider=_PacketProvider(
            {
                "deck": _result(
                    source_doc_id="deck",
                    provider_name="deck-provider",
                    fields=(_field("operations.aum", cast(str, 100.0), "deck", 0.8),),
                )
            }
        ),
        standard_library=library,
    )

    assert profile.per_doc_standard_element_coverage["deck"][0].detected is True


def test_packet_flags_missing_mandatory_elements() -> None:
    profile = ingest_packet(
        (PacketFile(document_id="deck", content=b"deck"),),
        provider=_PacketProvider(
            {
                "deck": _result(
                    source_doc_id="deck",
                    provider_name="deck-provider",
                    fields=(),
                )
            }
        ),
        standard_library=_library_for_doc_type("deck"),
    )

    assert profile.flagged_non_standard_items == ("deck:operations.aum:missing_mandatory",)


class _PacketProvider:
    def __init__(self, results: dict[str, ExtractedDocumentResult]) -> None:
        self._results = results

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        _ = content
        result = self._results[source_doc_id]
        return replace(result, source_doc_id=source_doc_id)


def _result(
    *,
    source_doc_id: str,
    provider_name: str,
    fields: tuple[ExtractedField, ...],
) -> ExtractedDocumentResult:
    return ExtractedDocumentResult(
        source_doc_id=source_doc_id,
        provider_name=provider_name,
        fields=fields,
    )


def _field(
    key: str,
    value: str,
    method: str,
    confidence: float,
) -> ExtractedField:
    return ExtractedField(
        key=key,
        value=value,
        confidence=confidence,
        source_doc_id="source",
        source_page=1,
        method=method,
    )


def _library_for_doc_type(doc_type: str):
    return load_standard_element_library(
        {
            "version": "packet-test",
            "non_authoritative": True,
            "doc_types": {
                doc_type: [
                    {
                        "key": "operations.aum",
                        "detector_name": "field_present",
                        "mandatory": True,
                    }
                ]
            },
        }
    )
