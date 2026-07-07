"""Tests for the optional Docling extraction provider."""

from __future__ import annotations

import pytest
from stranske_pdf_extract.providers.docling_provider import DoclingProvider

from inv_man_intake.extraction.providers.base import (
    ExtractionProvider,
    MultiModalExtractionProvider,
    validate_extracted_document_result,
)
from inv_man_intake.extraction.providers.docling_primary import (
    DoclingPrimaryExtractionProvider,
    MissingDoclingDependencyError,
)


class _FakeSharedDoclingProvider:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_modalities(self, source_doc_id: str, content: bytes) -> object:
        from inv_man_intake.extraction.providers.base import (
            ExtractedTextBlock,
            ProviderExtractionOutput,
            SourceLocation,
        )

        _ = content
        return ProviderExtractionOutput(
            source_doc_id=source_doc_id,
            provider_name="docling",
            text_blocks=(
                ExtractedTextBlock(
                    text=self._text,
                    location=SourceLocation(source_doc_id=source_doc_id, source_page=1),
                ),
            ),
        )


def test_docling_provider_conforms_to_protocol() -> None:
    provider = DoclingPrimaryExtractionProvider()

    assert isinstance(provider, ExtractionProvider)
    assert isinstance(provider, MultiModalExtractionProvider)
    assert isinstance(provider._provider, DoclingProvider)


def test_docling_provider_skips_cleanly_when_optional_dependency_absent() -> None:
    try:
        import docling  # type: ignore[import-untyped]  # noqa: F401
    except Exception:
        provider = DoclingPrimaryExtractionProvider()
        with pytest.raises(MissingDoclingDependencyError):
            provider.extract_modalities(source_doc_id="sample.pdf", content=b"%PDF-1.4\n%%EOF")
        return

    pytest.skip("real Docling conversion requires a known-good integration fixture")


def test_docling_provider_maps_docling_text_into_canonical_fields() -> None:
    provider = DoclingPrimaryExtractionProvider(
        provider=_FakeSharedDoclingProvider(
            "Strategy: Summit Arc Credit\n"
            "Management fee: 1.25%\n"
            "Performance fee: 10%\n"
            "Benchmark: S&P 500"
        )
    )

    result = provider.extract(source_doc_id="sample.pdf", content=b"%PDF-1.4\n%%EOF")

    validate_extracted_document_result(result)
    assert result.provider_name == "docling-primary"
    fields = {field.key: field for field in result.fields}
    assert fields["strategy.name"].value == "Summit Arc Credit"
    assert fields["terms.management_fee"].method == "docling-primary"
    assert fields["benchmark.name"].value == "S&P 500"
