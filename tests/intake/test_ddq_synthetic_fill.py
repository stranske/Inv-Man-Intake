"""Synthetic ILPA DDQ fixture and packet-pipeline test for issue #951.

This module provides a synthetic ILPA (Institutional Limited Partners Association)
Due Diligence Questionnaire (DDQ) fixture and tests to verify that:
1. Required DDQ fields are properly extracted through the packet pipeline
2. Required-field deletion causes validation to fail
3. Restoring required fields allows validation to pass
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inv_man_intake.extraction.doc_type import DocumentType
from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    SourceLocation,
)
from inv_man_intake.extraction.service import DefaultExtractionService, ProviderTransportBackend
from inv_man_intake.intake.standard_elements import (
    DataDrivenStandardElementLibrary,
    StandardElement,
)
from inv_man_intake.packet import PacketFile, ingest_packet

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "ddq_synthetic"
_COMPLETE_FIXTURE = _FIXTURE_DIR / "complete_ilpa_ddq.json"

# ILPA DDQ Standard Element Definitions
# These represent the typical fields found in an ILPA DDQ
_DDQ_ELEMENTS = (
    StandardElement(key="firm_name", detector_name="identity.firm_name", mandatory=True),
    StandardElement(key="fund_name", detector_name="identity.fund_name", mandatory=True),
    StandardElement(key="strategy", detector_name="thesis.strategy", mandatory=True),
    StandardElement(key="aum", detector_name="fundamentals.aum", mandatory=True),
    StandardElement(
        key="inception_date", detector_name="fundamentals.inception_date", mandatory=False
    ),
    StandardElement(key="management_fee", detector_name="terms.management_fee", mandatory=False),
    StandardElement(
        key="investment_minimum", detector_name="terms.investment_minimum", mandatory=True
    ),
    StandardElement(key="lockup_period", detector_name="terms.lockup_period", mandatory=False),
    StandardElement(
        key="redemption_frequency", detector_name="terms.redemption_frequency", mandatory=False
    ),
    StandardElement(key="auditor", detector_name="operations.auditor", mandatory=False),
    StandardElement(key="admin", detector_name="operations.admin", mandatory=False),
    StandardElement(key="custodian", detector_name="operations.custodian", mandatory=False),
)


def _default_detector_registry() -> Mapping[str, Any]:
    """Create a minimal detector registry that returns True for present fields."""

    def present_detector(payload: Mapping[str, Any]) -> bool:
        """Detector that checks if the field key exists in extracted fields."""
        field_key = payload.get("field_key")
        if not isinstance(field_key, str):
            return False
        fields = payload.get("fields", ())
        return field_key in fields

    return {elem.detector_name: present_detector for elem in _DDQ_ELEMENTS}


@dataclass(frozen=True)
class SyntheticIlpaDdqProvider:
    """Synthetic extraction provider that parses tracked DDQ fixture JSON content."""

    name: str = "synthetic-ilpa-ddq"
    confidence: float = 0.95

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        """Extract ILPA DDQ fields from synthetic JSON packet content."""
        payload = json.loads(content.decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("synthetic DDQ content must be a JSON object")
        fields_section = payload.get("fields")
        if not isinstance(fields_section, Mapping):
            raise ValueError("synthetic DDQ content must include a fields object")

        fields_list = [
            ExtractedField(
                key=key,
                value=str(value),
                confidence=self.confidence,
                source_doc_id=source_doc_id,
                source_page=1,
                method="synthetic",
                location=SourceLocation(source_doc_id=source_doc_id, source_page=1),
            )
            for key, value in fields_section.items()
        ]

        return ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            provider_name=self.name,
            fields=tuple(fields_list),
        )


# Create a standard element library with DDQ support
_DDQ_LIBRARY = DataDrivenStandardElementLibrary(
    version="1.0.0",
    non_authoritative=False,
    elements_by_doc_type={
        "ddq": _DDQ_ELEMENTS,
        "due_diligence_questionnaire": _DDQ_ELEMENTS,
    },
    detectors=_default_detector_registry(),
)


def _load_fixture_bytes(fixture_path: Path = _COMPLETE_FIXTURE) -> bytes:
    """Load tracked synthetic DDQ fixture content as packet bytes."""
    return fixture_path.read_bytes()


def _fixture_payload_without_field(field_name: str) -> bytes:
    """Return fixture JSON bytes with one field removed from the tracked fixture."""
    payload = json.loads(_COMPLETE_FIXTURE.read_text(encoding="utf-8"))
    fields = payload["fields"]
    del fields[field_name]
    return json.dumps(payload).encode("utf-8")


def _create_ddq_extraction_service(confidence: float = 0.95) -> DefaultExtractionService:
    """Create an extraction service with synthetic ILPA DDQ provider."""
    provider = SyntheticIlpaDdqProvider(confidence=confidence)
    return DefaultExtractionService(
        backend=ProviderTransportBackend(provider, transport_name="synthetic-ilpa-ddq")
    )


def _mandatory_coverage_keys(coverage: tuple[Any, ...]) -> set[str]:
    return {item.key for item in coverage if item.detected and item.mandatory}


def test_ddq_fields_extracted() -> None:
    """Test that synthetic ILPA DDQ fields are properly extracted through packet pipeline.

    This test verifies:
    1. A complete DDQ with all mandatory fields passes validation
    2. Deleting required fields causes validation to fail
    3. Restoring the required fields allows validation to pass again

    The test uses a synthetic ILPA DDQ fixture to simulate document extraction
    under the existing ontology contract.
    """
    extraction_service = _create_ddq_extraction_service()
    content = _load_fixture_bytes()
    packet_file = PacketFile(
        document_id="synthetic_ddq_001",
        content=content,
        filename="ilpa_ddq_test.pdf",
    )

    profile = ingest_packet(
        files=[packet_file],
        extraction_service=extraction_service,
        standard_library=_DDQ_LIBRARY,
        packet_id="test-ilpa-ddq-complete",
    )

    assert len(profile.documents) == 1
    doc_profile = profile.documents[0]
    assert doc_profile.document_id == "synthetic_ddq_001"

    mandatory_fields = {elem.key for elem in _DDQ_ELEMENTS if elem.mandatory}
    detected_mandatory = _mandatory_coverage_keys(doc_profile.standard_element_coverage)
    assert detected_mandatory == mandatory_fields

    content_incomplete = _fixture_payload_without_field("investment_minimum")
    packet_file_incomplete = PacketFile(
        document_id="synthetic_ddq_002",
        content=content_incomplete,
        filename="ilpa_ddq_incomplete.pdf",
    )

    profile_incomplete = ingest_packet(
        files=[packet_file_incomplete],
        extraction_service=extraction_service,
        standard_library=_DDQ_LIBRARY,
        packet_id="test-ilpa-ddq-incomplete",
    )

    doc_incomplete = profile_incomplete.documents[0]
    investment_min_coverage = next(
        (c for c in doc_incomplete.standard_element_coverage if c.key == "investment_minimum"),
        None,
    )

    assert investment_min_coverage is not None
    assert investment_min_coverage.mandatory is True
    assert investment_min_coverage.detected is False
    assert (
        "synthetic_ddq_002:investment_minimum:missing_mandatory"
        in profile_incomplete.flagged_non_standard_items
    )

    packet_file_restored = PacketFile(
        document_id="synthetic_ddq_003",
        content=_load_fixture_bytes(),
        filename="ilpa_ddq_restored.pdf",
    )

    profile_restored = ingest_packet(
        files=[packet_file_restored],
        extraction_service=extraction_service,
        standard_library=_DDQ_LIBRARY,
        packet_id="test-ilpa-ddq-restored",
    )

    assert len(profile_restored.documents) == 1
    doc_profile_restored = profile_restored.documents[0]
    assert doc_profile_restored.document_id == "synthetic_ddq_003"

    investment_min_coverage_restored = next(
        (
            c
            for c in doc_profile_restored.standard_element_coverage
            if c.key == "investment_minimum"
        ),
        None,
    )

    assert investment_min_coverage_restored is not None
    assert investment_min_coverage_restored.mandatory is True
    assert investment_min_coverage_restored.detected is True


def test_ddq_required_fields_contract() -> None:
    """Test that DDQ required fields are properly defined in the ontology contract."""
    mandatory_ddq_fields = {elem.key for elem in _DDQ_ELEMENTS if elem.mandatory}

    expected_mandatory = {"firm_name", "fund_name", "strategy", "aum", "investment_minimum"}

    assert (
        mandatory_ddq_fields == expected_mandatory
    ), f"Mandatory DDQ fields mismatch: {mandatory_ddq_fields} != {expected_mandatory}"


def test_ddq_document_type_classification() -> None:
    """Test that DDQ document type is properly classified."""
    from inv_man_intake.extraction.doc_type import classify_doc_type

    ddq_strings = [
        "ILPA DDQ",
        "Due Diligence Questionnaire",
        "ddq",
        "ILPA Due Diligence Questionnaire",
    ]

    for text in ddq_strings:
        doc_type = classify_doc_type(text, standard_library=None)
        assert (
            doc_type == DocumentType.DDQ
        ), f"Text '{text}' should be classified as DDQ, got {doc_type}"


# Make the library available for other tests
_DDQ_TEST_LIBRARY = _DDQ_LIBRARY
