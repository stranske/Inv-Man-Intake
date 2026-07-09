"""Extraction service port and swappable transport adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractionProvider,
)


@runtime_checkable
class TransportBackend(Protocol):
    """Backend capable of resolving one document through the service port."""

    @property
    def name(self) -> str: ...

    def extract_document(self, *, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        """Extract fields from document bytes."""


@runtime_checkable
class ExtractionService(Protocol):
    """Stable extraction port used by packet and app consumers."""

    @property
    def backend_name(self) -> str: ...

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        """Extract one document through the selected backend transport."""


@dataclass(frozen=True)
class ProviderTransportBackend:
    """Adapt an in-process provider to the transport backend seam."""

    provider: ExtractionProvider
    transport_name: str | None = None

    @property
    def name(self) -> str:
        return self.transport_name or self.provider.name

    def extract_document(self, *, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        return self.provider.extract(source_doc_id=source_doc_id, content=content)


class PyodideLightTransportBackend(ProviderTransportBackend):
    """Current Tier-A backend: in-process, no egress, browser-bundle viable."""

    def __init__(self, provider: ExtractionProvider) -> None:
        super().__init__(provider=provider, transport_name="pyodide-light")


@dataclass(frozen=True)
class StubServiceTransportBackend:
    """Documented future service/server backend shape without network behavior."""

    name: str
    endpoint: str

    def extract_document(self, *, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        _ = source_doc_id, content
        raise NotImplementedError(
            f"{self.name} transport is a documented future adapter for {self.endpoint}"
        )


@dataclass(frozen=True)
class DefaultExtractionService:
    """Concrete service port that delegates to a selected backend transport."""

    backend: TransportBackend

    @property
    def backend_name(self) -> str:
        return self.backend.name

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        return self.backend.extract_document(source_doc_id=source_doc_id, content=content)


def ensure_extraction_service(candidate: object) -> ExtractionService:
    """Accept a service, or adapt a legacy provider into the service port."""

    if isinstance(candidate, ExtractionService):
        return candidate
    if isinstance(candidate, ExtractionProvider):
        return DefaultExtractionService(backend=ProviderTransportBackend(candidate))
    if callable(getattr(candidate, "extract", None)):
        return DefaultExtractionService(
            backend=ProviderTransportBackend(
                cast(ExtractionProvider, candidate),
                transport_name=type(candidate).__name__,
            )
        )
    raise TypeError("expected an ExtractionService or legacy ExtractionProvider")


def build_pyodide_light_service(file_name: str) -> ExtractionService:
    """Create the default no-egress extraction service for current app paths."""

    from inv_man_intake.extraction.providers.pdf_primary import PdfPrimaryExtractionProvider
    from inv_man_intake.extraction.providers.pptx_primary import PptxPrimaryExtractionProvider

    provider: ExtractionProvider
    if file_name.lower().endswith(".pptx"):
        provider = PptxPrimaryExtractionProvider()
    else:
        provider = PdfPrimaryExtractionProvider()
    return DefaultExtractionService(backend=PyodideLightTransportBackend(provider))


def build_docling_service(*, do_ocr: bool = False) -> ExtractionService:
    """Create the optional local Docling service behind the same port."""

    from inv_man_intake.extraction.providers.docling_primary import DoclingPrimaryExtractionProvider

    return DefaultExtractionService(
        backend=ProviderTransportBackend(
            provider=DoclingPrimaryExtractionProvider(do_ocr=do_ocr),
            transport_name="docling-local",
        )
    )


def build_future_localhost_service(endpoint: str) -> ExtractionService:
    return DefaultExtractionService(
        backend=StubServiceTransportBackend(name="localhost-service", endpoint=endpoint)
    )


def build_future_remote_service(endpoint: str) -> ExtractionService:
    return DefaultExtractionService(
        backend=StubServiceTransportBackend(name="remote-service", endpoint=endpoint)
    )


def extraction_service_extractor(
    service: ExtractionService,
) -> Callable[[dict[str, object]], dict[str, ExtractedDocumentResult]]:
    """Adapt the service port to the existing orchestrator callable shape."""

    def extract(payload: dict[str, object]) -> dict[str, ExtractedDocumentResult]:
        content = payload["content"]
        if not isinstance(content, (bytes, bytearray)):
            raise TypeError("document content must be bytes")
        return {
            "result": service.extract(
                source_doc_id=str(payload["document_id"]),
                content=bytes(content),
            )
        }

    return extract


__all__ = [
    "DefaultExtractionService",
    "ExtractionService",
    "ProviderTransportBackend",
    "PyodideLightTransportBackend",
    "StubServiceTransportBackend",
    "TransportBackend",
    "build_docling_service",
    "build_future_localhost_service",
    "build_future_remote_service",
    "build_pyodide_light_service",
    "ensure_extraction_service",
    "extraction_service_extractor",
]
