"""Tests for real-byte PDF primary extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractionProvider,
    validate_extracted_document_result,
)
from inv_man_intake.extraction.providers.pdf_primary import (
    PdfPrimaryExtractionProvider,
    UnsupportedDocumentFormatError,
)

_FIXTURE_ROOT = Path("tests/fixtures/extraction")


def test_pdf_primary_provider_extracts_real_pdf_bytes_with_provenance() -> None:
    provider = PdfPrimaryExtractionProvider()
    assert isinstance(provider, ExtractionProvider)

    result = provider.extract(
        source_doc_id="doc_pdf_1",
        content=(_FIXTURE_ROOT / "summit_arc_investment_update.pdf").read_bytes(),
    )

    assert isinstance(result, ExtractedDocumentResult)
    assert result.provider_name == "pdf-primary"
    validate_extracted_document_result(result)
    fields = {field.key: field for field in result.fields}
    assert fields["strategy.asset_class"].value == "credit"
    assert fields["strategy.asset_class"].source_page == 2
    assert fields["terms.management_fee"].value == "1.25%"
    assert any(field.source_page > 0 for field in result.fields)


def test_pdf_primary_provider_returns_empty_result_for_no_match_pdf() -> None:
    provider = PdfPrimaryExtractionProvider()

    result = provider.extract(
        source_doc_id="doc_pdf_empty",
        content=(_FIXTURE_ROOT / "empty_text_only.pdf").read_bytes(),
    )

    assert result.fields == ()
    validate_extracted_document_result(result)


def test_pdf_primary_provider_rejects_non_pdf_bytes() -> None:
    provider = PdfPrimaryExtractionProvider()

    with pytest.raises(UnsupportedDocumentFormatError, match="only supports PDF bytes"):
        provider.extract(
            source_doc_id="doc_xlsx",
            content=(_FIXTURE_ROOT / "summit_arc_track_record.xlsx").read_bytes(),
        )


def test_pdf_primary_provider_rejects_pdf_without_eof_marker() -> None:
    provider = PdfPrimaryExtractionProvider()
    broken_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"

    with pytest.raises(UnsupportedDocumentFormatError, match="only supports PDF bytes"):
        provider.extract(source_doc_id="doc_pdf_broken", content=broken_pdf)


def test_pdf_primary_provider_uses_literals_from_stream_blocks_only() -> None:
    provider = PdfPrimaryExtractionProvider()
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Length 40 >>\nstream\n"
        b"(Page 2) (Management fee: 2.00%) Tj\n"
        b"endstream\n"
        b"endobj\n"
        b"(Management fee: 9.99%)\n"
        b"%%EOF"
    )

    result = provider.extract(source_doc_id="doc_pdf_stream_only", content=content)
    fields = {field.key: field for field in result.fields}
    assert fields["terms.management_fee"].value == "2.00%"
