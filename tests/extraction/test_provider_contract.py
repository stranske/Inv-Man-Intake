"""Conformance tests for extraction provider contract."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractionProvider
from inv_man_intake.extraction.providers.primary import PrimaryRegexExtractionProvider


def _fixture_bytes() -> bytes:
    fixture = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "extraction"
        / "sample_manager_package.txt"
    )
    return fixture.read_bytes()


def test_primary_provider_returns_canonical_result_shape() -> None:
    provider = PrimaryRegexExtractionProvider()
    assert isinstance(provider, ExtractionProvider)
    result = provider.extract(source_doc_id="doc_1", content=_fixture_bytes())

    assert isinstance(result, ExtractedDocumentResult)
    assert result.source_doc_id == "doc_1"
    assert result.provider_name == "primary-regex"
    assert len(result.fields) >= 3


def test_primary_provider_fields_include_required_metadata() -> None:
    provider = PrimaryRegexExtractionProvider()
    result = provider.extract(source_doc_id="doc_2", content=_fixture_bytes())

    for field in result.fields:
        assert field.source_doc_id == "doc_2"
        assert field.source_page >= 1
        assert 0.0 <= field.confidence <= 1.0
        assert field.key
        assert field.value


def test_primary_provider_extracts_expected_baseline_keys() -> None:
    provider = PrimaryRegexExtractionProvider()
    result = provider.extract(source_doc_id="doc_3", content=_fixture_bytes())
    keys = {field.key for field in result.fields}

    assert "terms.management_fee" in keys
    assert "terms.performance_fee" in keys
    assert "strategy.name" in keys
    assert "benchmark.name" in keys
