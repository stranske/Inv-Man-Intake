"""Tests for the optional Docling extraction provider."""

from __future__ import annotations

import pytest

from inv_man_intake.extraction.providers.base import (
    ExtractionProvider,
    MultiModalExtractionProvider,
    validate_extracted_document_result,
    validate_provider_output,
)
from inv_man_intake.extraction.providers.docling_primary import (
    DoclingPrimaryExtractionProvider,
    MissingDoclingDependencyError,
)


class _FakeDoclingDocument:
    def __init__(self, text: str) -> None:
        self._text = text

    def export_to_markdown(self) -> str:
        return self._text


class _FakeDoclingResult:
    def __init__(self, text: str) -> None:
        self.document = _FakeDoclingDocument(text)


class _FakeDoclingConverter:
    def __init__(self, text: str) -> None:
        self._text = text

    def convert(self, source: object) -> _FakeDoclingResult:
        _ = source
        return _FakeDoclingResult(self._text)


def test_docling_provider_conforms_to_protocol() -> None:
    provider = DoclingPrimaryExtractionProvider()

    assert isinstance(provider, ExtractionProvider)
    assert isinstance(provider, MultiModalExtractionProvider)


def test_docling_provider_skips_cleanly_when_optional_dependency_absent() -> None:
    pytest.importorskip("docling")

    provider = DoclingPrimaryExtractionProvider()
    try:
        output = provider.extract_modalities(source_doc_id="sample.pdf", content=b"%PDF-1.4\n%%EOF")
    except MissingDoclingDependencyError as exc:  # pragma: no cover - defensive import race
        pytest.skip(str(exc))
    validate_provider_output(output)


def test_docling_provider_maps_docling_text_into_canonical_fields() -> None:
    provider = DoclingPrimaryExtractionProvider(
        converter=_FakeDoclingConverter(
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
