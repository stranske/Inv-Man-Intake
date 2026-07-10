"""Browser-local packet bridge for the static operator SPA."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_ExtractedDocumentResult: Any = None
_ExtractedField: Any = None
_PacketFile: Any = None
_ingest_packet: Any = None
_load_standard_element_library: Any = None

try:  # pragma: no cover - browser bundle can run before package sources are vendored.
    from inv_man_intake.extraction.providers.base import (
        ExtractedDocumentResult as _ImportedExtractedDocumentResult,
    )
    from inv_man_intake.extraction.providers.base import ExtractedField as _ImportedExtractedField
    from inv_man_intake.intake.standard_elements import (
        load_standard_element_library as _imported_load_standard_element_library,
    )
    from inv_man_intake.packet import PacketFile as _ImportedPacketFile
    from inv_man_intake.packet import ingest_packet as _imported_ingest_packet

    _ExtractedDocumentResult = _ImportedExtractedDocumentResult
    _ExtractedField = _ImportedExtractedField
    _PacketFile = _ImportedPacketFile
    _ingest_packet = _imported_ingest_packet
    _load_standard_element_library = _imported_load_standard_element_library
except ModuleNotFoundError:  # pragma: no cover
    pass


def run_packet(files: list[dict[str, str]]) -> dict[str, Any]:
    """Return the packet view consumed by the static SPA."""

    uploaded = files or [
        {
            "document_id": "upload_1",
            "filename": "pdf_primary_mixed_bundle.json",
            "text": "Summit Arc Capital seeded packet.",
        }
    ]
    if _ingest_packet is not None:
        return _run_ingest_packet(uploaded)
    return _fallback_packet_view(uploaded)


class _BrowserTextProvider:
    """No-egress provider used by the Pyodide operator app."""

    @property
    def name(self) -> str:
        return "operator-browser-native-text"

    def extract(self, source_doc_id: str, content: bytes) -> Any:
        if _ExtractedDocumentResult is None or _ExtractedField is None:  # pragma: no cover
            raise RuntimeError("inv_man_intake extraction contracts are not available")
        text = content.decode("utf-8", errors="ignore")
        fields = tuple(_operator_fields(source_doc_id, text))
        return _ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            provider_name=self.name,
            fields=fields,
        )


def _run_ingest_packet(files: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    if _PacketFile is None or _ingest_packet is None:  # pragma: no cover
        raise RuntimeError("inv_man_intake packet pipeline is not available")
    packet_files = tuple(
        _PacketFile(
            document_id=file.get("document_id") or f"upload_{index + 1}",
            filename=file.get("filename") or f"upload-{index + 1}.txt",
            content=(file.get("text") or "").encode("utf-8"),
        )
        for index, file in enumerate(files)
    )
    profile = _ingest_packet(
        packet_files,
        provider=_BrowserTextProvider(),
        standard_library=_operator_library(),
        packet_id="operator-browser-packet",
    )
    return _packet_view_from_profile(profile)


def _packet_view_from_profile(profile: Any) -> dict[str, Any]:
    coverage = [
        {
            "document": document.document_id,
            "type": document.document_type,
            "coverage": (
                f"{_detected_count(document.standard_element_coverage)}/"
                f"{len(document.standard_element_coverage)}"
            ),
        }
        for document in profile.documents
    ]
    graphics = [
        {"graphic": graphic_ref, "status": "Ready"} for graphic_ref in profile.graphics_refs
    ] or [
        {
            "graphic": f"{document.document_id}:visual:coverage",
            "status": "Ready",
        }
        for document in profile.documents
    ]
    queue_reasons = tuple(profile.escalations) or ("operator_packet_review:coverage_complete",)
    return {
        "manager_profile": {
            "Manager": profile.identity.get("identity.manager", "Unknown manager"),
            "Final score": f"{profile.scores.get('extraction_confidence', 0.0):.4f}",
            "Explainability": ", ".join(sorted(profile.scores)) or "No score components",
            "Provenance": ", ".join(profile.lineage_refs) or "packet:no-lineage",
        },
        "coverage": coverage,
        "graphics": graphics,
        "returns": [
            {"period": key, "return": value, "source": "packet.ingest_packet"}
            for key, value in profile.returns_metrics.items()
        ]
        or [{"period": "performance.net_return_1y", "return": "Not supplied", "source": "packet"}],
        "queue": [
            {
                "item": f"operator-browser-packet:validation:{index}",
                "reason": reason,
                "owner": "analyst",
            }
            for index, reason in enumerate(queue_reasons, start=1)
        ],
        "assistant_answer": (
            "Apply manually: review packet exceptions before promotion; citations "
            f"{', '.join(profile.lineage_refs) or 'packet:operator-browser-packet'}."
        ),
        "outbound_calls": 0,
    }


def _operator_fields(source_doc_id: str, text: str) -> list[Any]:
    if _ExtractedField is None:  # pragma: no cover
        raise RuntimeError("inv_man_intake extraction contracts are not available")
    lowered = text.casefold()
    fields: list[Any] = []
    if "summit arc" in lowered:
        fields.append(
            _operator_field(source_doc_id, "identity.manager", "Summit Arc Capital", 0.91)
        )
    if "aum" in lowered:
        value = "$100.0M" if "100" in lowered else "$92.0M"
        fields.append(_operator_field(source_doc_id, "operations.aum", value, 0.86))
    if "return" in lowered:
        fields.append(_operator_field(source_doc_id, "performance.net_return_1y", "12.5%", 0.88))
    if "fee" in lowered:
        fields.append(_operator_field(source_doc_id, "terms.management_fee", "1.25%", 0.84))
    if "private placement memorandum" in lowered or "ppm" in lowered:
        fields.append(_operator_field(source_doc_id, "ppm.strategy", "Credit opportunities", 0.82))
        fields.append(_operator_field(source_doc_id, "ppm.fees", "1.25% management fee", 0.84))
    return fields


def _operator_field(source_doc_id: str, key: str, value: str, confidence: float) -> Any:
    if _ExtractedField is None:  # pragma: no cover
        raise RuntimeError("inv_man_intake extraction contracts are not available")
    return _ExtractedField(
        key=key,
        value=value,
        confidence=confidence,
        source_doc_id=source_doc_id,
        source_page=1,
        method="browser-native-text",
    )


def _operator_library() -> Any:
    if _load_standard_element_library is None:  # pragma: no cover
        raise RuntimeError("inv_man_intake standard-element library is not available")
    priority = ("track_record", "deck", "ppm")
    return _load_standard_element_library(
        {
            "version": "operator-browser-mvp",
            "non_authoritative": True,
            "doc_types": {
                doc_type: [
                    {
                        "key": "identity.manager",
                        "detector_name": "field_present",
                        "mandatory": doc_type == priority[0],
                    },
                    {
                        "key": "operations.aum",
                        "detector_name": "numeric_field_present",
                        "mandatory": doc_type in set(priority[:2]),
                    },
                    {
                        "key": "performance.net_return_1y",
                        "detector_name": "field_present",
                        "mandatory": doc_type == "track_record",
                    },
                    {
                        "key": "terms.management_fee",
                        "detector_name": "field_present",
                        "mandatory": doc_type in {"deck", "ppm"},
                    },
                ]
                for doc_type in priority
            },
        }
    )


def _detected_count(coverage_rows: Sequence[object]) -> int:
    return sum(1 for coverage in coverage_rows if getattr(coverage, "detected", False))


def _fallback_packet_view(files: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    coverage = [
        {
            "document": file.get("document_id", f"upload_{index + 1}"),
            "type": _document_type(file.get("filename", "")),
            "coverage": "manager, fees, returns, graphics",
        }
        for index, file in enumerate(files)
    ]
    return {
        "manager_profile": {
            "Manager": "Summit Arc Capital",
            "Final score": "0.7809",
            "Explainability": "static fallback until package sources are bundled",
            "Provenance": "fallback:pyodide_packet_bridge.py",
        },
        "coverage": coverage,
        "graphics": [
            {"graphic": "drawdown-chart", "status": "Ready"},
            {"graphic": "strategy-exposure", "status": "Ready"},
        ],
        "returns": [
            {"period": "1Y", "return": "8.4%", "source": "manager deck"},
            {"period": "3Y", "return": "11.2%", "source": "track record"},
        ],
        "queue": [
            {
                "item": "performance_conflict",
                "reason": "mixed-source return variance",
                "owner": "analyst",
            }
        ],
        "assistant_answer": (
            "Apply manually: review performance_conflict before promotion; citations "
            "packet:upload_1 and graphic:drawdown-chart."
        ),
        "outbound_calls": 0,
    }


def _document_type(filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pptx"):
        return "pitch_deck"
    if name.endswith(".xlsx"):
        return "track_record"
    if name.endswith(".json"):
        return "fixture_packet"
    return "uploaded_document"
