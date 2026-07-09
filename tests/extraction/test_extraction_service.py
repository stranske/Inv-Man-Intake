"""Tests for the ExtractionService port and transport boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.extraction.service import (
    DefaultExtractionService,
    ProviderTransportBackend,
    PyodideLightTransportBackend,
    build_future_localhost_service,
    build_future_remote_service,
    extraction_service_extractor,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_is_swappable() -> None:
    content = b"Manager: Summit Arc\nAUM: $42M"
    source_doc_id = "sample-manager.pdf"
    pyodide_service = DefaultExtractionService(
        backend=PyodideLightTransportBackend(_StaticProvider())
    )
    service_backend = DefaultExtractionService(
        backend=ProviderTransportBackend(
            provider=_StaticProvider(),
            transport_name="localhost-service-fake",
        )
    )

    pyodide_result = pyodide_service.extract(source_doc_id=source_doc_id, content=content)
    service_result = service_backend.extract(source_doc_id=source_doc_id, content=content)

    assert pyodide_result == service_result
    assert pyodide_service.backend_name == "pyodide-light"
    assert service_backend.backend_name == "localhost-service-fake"


def test_orchestrator_adapter_uses_service_api() -> None:
    service = DefaultExtractionService(backend=PyodideLightTransportBackend(_StaticProvider()))
    extractor = extraction_service_extractor(service)

    payload = extractor({"document_id": "doc-1", "content": b"AUM: $42M"})

    assert payload["result"].source_doc_id == "doc-1"
    assert payload["result"].fields[0].value == "$42M"


def test_future_service_backends_are_documented_stubs() -> None:
    localhost = build_future_localhost_service("http://127.0.0.1:8765/extract")
    remote = build_future_remote_service("https://extract.example.test")

    with pytest.raises(NotImplementedError, match="localhost-service"):
        localhost.extract("doc", b"payload")
    with pytest.raises(NotImplementedError, match="remote-service"):
        remote.extract("doc", b"payload")


def test_consumers_do_not_import_concrete_extractors_directly() -> None:
    consumer_sources = (
        _REPO_ROOT / "src/inv_man_intake/packet.py",
        _REPO_ROOT / "src/inv_man_intake/v1_smoke.py",
    )
    banned_tokens = (
        "PdfPrimaryExtractionProvider",
        "PptxPrimaryExtractionProvider",
        "PrimaryRegexExtractionProvider",
        "DoclingPrimaryExtractionProvider",
        "from inv_man_intake.extraction.providers.pdf_primary",
        "from inv_man_intake.extraction.providers.pptx_primary",
        "from inv_man_intake.extraction.providers.primary",
        "from inv_man_intake.extraction.providers.docling_primary",
    )

    for source_path in consumer_sources:
        source = source_path.read_text()
        assert not any(token in source for token in banned_tokens), source_path


class _StaticProvider:
    def __init__(self, name: str = "static-provider") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        _ = content
        return ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            provider_name=self.name,
            fields=(
                ExtractedField(
                    key="operations.aum",
                    value="$42M",
                    confidence=0.91,
                    source_doc_id=source_doc_id,
                    source_page=1,
                    method=self.name,
                ),
            ),
        )
