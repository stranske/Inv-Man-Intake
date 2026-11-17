"""Tests for real-byte PPTX primary extraction."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractionProvider,
    validate_extracted_document_result,
)
from inv_man_intake.extraction.providers.pdf_primary import UnsupportedDocumentFormatError
from inv_man_intake.extraction.providers.pptx_primary import PptxPrimaryExtractionProvider

_FIXTURE_ROOT = Path("tests/fixtures/extraction")


def test_pptx_primary_provider_satisfies_extraction_protocol() -> None:
    provider = PptxPrimaryExtractionProvider()
    assert isinstance(provider, ExtractionProvider)
    assert provider.name == "pptx-primary"


def test_pptx_primary_provider_extracts_real_pptx_bytes_with_provenance() -> None:
    provider = PptxPrimaryExtractionProvider()

    result = provider.extract(
        source_doc_id="doc_pptx_1",
        content=(_FIXTURE_ROOT / "harborline_strategy_review.pptx").read_bytes(),
    )

    assert isinstance(result, ExtractedDocumentResult)
    assert result.provider_name == "pptx-primary"
    validate_extracted_document_result(result)
    fields = {field.key: field for field in result.fields}
    assert fields["strategy.asset_class"].value == "credit"
    assert fields["strategy.asset_class"].source_page == 1
    assert fields["terms.management_fee"].value == "1.25%"
    assert fields["operations.aum"].value == "$750M"
    assert fields["operations.aum"].source_page == 2
    assert all(field.source_page >= 1 for field in result.fields)


def test_pptx_primary_provider_rejects_non_pptx_bytes() -> None:
    provider = PptxPrimaryExtractionProvider()

    with pytest.raises(UnsupportedDocumentFormatError, match="only supports PPTX bytes"):
        provider.extract(
            source_doc_id="doc_pdf",
            content=(_FIXTURE_ROOT / "summit_arc_investment_update.pdf").read_bytes(),
        )


def test_pptx_primary_provider_rejects_bare_zip_without_presentation_part() -> None:
    provider = PptxPrimaryExtractionProvider()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("docProps/core.xml", "<core/>")
    bare_zip = buffer.getvalue()
    assert bare_zip.startswith(b"PK\x03\x04")

    with pytest.raises(UnsupportedDocumentFormatError, match="only supports PPTX bytes"):
        provider.extract(source_doc_id="doc_bare_zip", content=bare_zip)


def test_pptx_primary_provider_rejects_malformed_slide_xml() -> None:
    provider = PptxPrimaryExtractionProvider()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<presentation/>")
        archive.writestr("ppt/slides/slide1.xml", "<broken")
    malformed = buffer.getvalue()

    with pytest.raises(UnsupportedDocumentFormatError, match="only supports PPTX bytes"):
        provider.extract(source_doc_id="doc_bad_slide_xml", content=malformed)


def test_pptx_primary_provider_ignores_zero_indexed_slide_for_one_based_provenance() -> None:
    provider = PptxPrimaryExtractionProvider()
    slide = (
        '<sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        "<a:t>strategy asset class: {value}</a:t></sld>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<presentation/>")
        archive.writestr("ppt/slides/slide0.xml", slide.format(value="zero"))
        archive.writestr("ppt/slides/slide1.xml", slide.format(value="one"))
    content = buffer.getvalue()

    result = provider.extract(source_doc_id="doc_zero_slide", content=content)

    fields = {field.key: field for field in result.fields}
    assert fields["strategy.asset_class"].value == "one"
    assert fields["strategy.asset_class"].source_page == 1
    assert all(field.source_page >= 1 for field in result.fields)


def test_pptx_monthly_return_rows_follow_presentation_order_not_part_names() -> None:
    provider = PptxPrimaryExtractionProvider()
    slide = (
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>"
        "MONTHLY_RETURN as_of={as_of} value=0.01 frequency=monthly"
        "</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    presentation = (
        '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<p:sldIdLst><p:sldId id="256" r:id="rId7"/><p:sldId id="257" r:id="rId2"/>'
        "</p:sldIdLst></p:presentation>"
    )
    slide_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
    rels = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId2" Type="{slide_type}" Target="slides/slide2.xml"/>'
        f'<Relationship Id="rId7" Type="{slide_type}" Target="/ppt/slides/slide7.xml"/>'
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/_rels/presentation.xml.rels", rels)
        archive.writestr("ppt/slides/slide2.xml", slide.format(as_of="2024-02-29"))
        archive.writestr("ppt/slides/slide7.xml", slide.format(as_of="2024-01-31"))
        archive.writestr("ppt/slides/slide9.xml", slide.format(as_of="2024-03-31"))

    result = provider.monthly_return_rows("doc_reordered", buffer.getvalue())

    pages = {row.as_of: row.source_page for row in result.rows}
    assert pages == {"2024-01-31": 1, "2024-02-29": 2}
    assert result.unsupported_lines == ()
