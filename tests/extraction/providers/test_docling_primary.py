"""Tests for the optional Docling extraction provider."""

from __future__ import annotations

import importlib.util

import pytest

from inv_man_intake.extraction.providers.base import (
    ExtractionProvider,
    MultiModalExtractionProvider,
    ProviderExtractionOutput,
    validate_extracted_document_result,
)
from inv_man_intake.extraction.providers.docling_primary import (
    DoclingPrimaryExtractionProvider,
    MissingDoclingDependencyError,
    _load_docling_provider_class,
)


class _FakeSharedDoclingProvider:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_modalities(self, source_doc_id: str, content: bytes) -> ProviderExtractionOutput:
        from inv_man_intake.extraction.providers.base import (
            ExtractedTextBlock,
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
    if importlib.util.find_spec("docling") is None:
        pytest.skip("extraction-docling extra or Docling dependency is required")

    docling_provider_class = _load_docling_provider_class()
    provider = DoclingPrimaryExtractionProvider()

    assert isinstance(provider, ExtractionProvider)
    assert isinstance(provider, MultiModalExtractionProvider)
    assert isinstance(provider._provider, docling_provider_class)


def test_docling_provider_deliberate_break_fails_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    class _TemporarilyBrokenDoclingProvider(DoclingPrimaryExtractionProvider):
        pass

    monkeypatch.setattr(_TemporarilyBrokenDoclingProvider, "extract", None)
    broken_provider = _TemporarilyBrokenDoclingProvider(
        provider=_FakeSharedDoclingProvider("Strategy: Test")
    )

    assert not isinstance(broken_provider, ExtractionProvider)
    assert not isinstance(broken_provider, MultiModalExtractionProvider)


def test_docling_provider_protocol_restored_after_deliberate_break() -> None:
    provider = DoclingPrimaryExtractionProvider(
        provider=_FakeSharedDoclingProvider("Strategy: Test")
    )

    assert isinstance(provider, ExtractionProvider)
    assert isinstance(provider, MultiModalExtractionProvider)


def test_docling_provider_skips_cleanly_when_optional_dependency_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _missing_docling_provider_class() -> type[object]:
        raise MissingDoclingDependencyError(
            "Install inv-man-intake[extraction-docling] to use DoclingPrimaryExtractionProvider"
        )

    monkeypatch.setattr(
        "inv_man_intake.extraction.providers.docling_primary._load_docling_provider_class",
        _missing_docling_provider_class,
    )

    with pytest.raises(MissingDoclingDependencyError, match="extraction-docling"):
        DoclingPrimaryExtractionProvider()


def test_core_provider_imports_do_not_load_docling() -> None:
    from inv_man_intake.extraction.providers import PdfPrimaryExtractionProvider
    from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider

    assert PrimaryRegexExtractionProvider().name == "primary-regex"
    assert PdfPrimaryExtractionProvider().name == "pdf-primary"


def test_custom_provider_rejects_do_ocr_flag() -> None:
    with pytest.raises(ValueError, match="do_ocr is only supported"):
        DoclingPrimaryExtractionProvider(
            provider=_FakeSharedDoclingProvider("Strategy: Test"),
            do_ocr=True,
        )


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
