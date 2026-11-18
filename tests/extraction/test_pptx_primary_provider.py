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
from inv_man_intake.extraction.service import read_pptx_monthly_return_rows

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


_ORDERED_SLIDE = (
    '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    "<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>"
    "MONTHLY_RETURN as_of=2024-01-31 value=0.01 frequency=monthly"
    "</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
)
_ORDERED_PRESENTATION = (
    '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<p:sldIdLst><p:sldId id="256" r:id="{rel_id}"/></p:sldIdLst></p:presentation>'
)
_ORDERED_RELS = (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
    'Target="slides/slide1.xml"/></Relationships>'
)
_RELS_PART = "ppt/_rels/presentation.xml.rels"


def _ordered_deck(
    *,
    presentation: str = _ORDERED_PRESENTATION.format(rel_id="rId1"),
    rels: str | None = _ORDERED_RELS,
    corrupt_member: str | None = None,
) -> bytes:
    """Build a one-slide ordered deck, optionally flipping a stored byte to break one CRC."""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("ppt/presentation.xml", presentation)
        if rels is not None:
            archive.writestr(_RELS_PART, rels)
        archive.writestr("ppt/slides/slide1.xml", _ORDERED_SLIDE)
    content = bytearray(buffer.getvalue())
    if corrupt_member is not None:
        with zipfile.ZipFile(io.BytesIO(bytes(content))) as archive:
            info = archive.getinfo(corrupt_member)
        header = info.header_offset
        name_length = int.from_bytes(content[header + 26 : header + 28], "little")
        extra_length = int.from_bytes(content[header + 28 : header + 30], "little")
        data_start = header + 30 + name_length + extra_length
        content[data_start] ^= 0x01
    return bytes(content)


def test_ordered_deck_fixture_is_readable_without_corruption() -> None:
    content = _ordered_deck()

    result = PptxPrimaryExtractionProvider().monthly_return_rows("doc_ok", content)
    via_service = read_pptx_monthly_return_rows("doc_ok", content)

    assert [(row.as_of, row.source_page) for row in result.rows] == [("2024-01-31", 1)]
    assert via_service == result


@pytest.mark.parametrize(
    "member",
    ["ppt/presentation.xml", _RELS_PART, "ppt/slides/slide1.xml"],
)
def test_pptx_monthly_return_rows_reject_bad_crc_member(member: str) -> None:
    content = _ordered_deck(corrupt_member=member)
    with (
        zipfile.ZipFile(io.BytesIO(content)) as archive,
        pytest.raises(zipfile.BadZipFile, match="CRC"),
    ):
        archive.read(member)

    with pytest.raises(UnsupportedDocumentFormatError, match="only supports PPTX bytes") as excinfo:
        PptxPrimaryExtractionProvider().monthly_return_rows("doc_bad_crc", content)

    assert isinstance(excinfo.value.__cause__, zipfile.BadZipFile)
    assert read_pptx_monthly_return_rows("doc_bad_crc", content) is None


@pytest.mark.parametrize(
    ("presentation", "rels"),
    [
        pytest.param(_ORDERED_PRESENTATION.format(rel_id="rId1"), None, id="missing-rels-part"),
        pytest.param(_ORDERED_PRESENTATION.format(rel_id="rId9"), _ORDERED_RELS, id="dangling-id"),
        pytest.param(_ORDERED_PRESENTATION.format(rel_id=""), _ORDERED_RELS, id="empty-id"),
        pytest.param(
            _ORDERED_PRESENTATION.format(rel_id="rId1"),
            _ORDERED_RELS.replace("slides/slide1.xml", "slides/slide4.xml"),
            id="target-part-absent",
        ),
        pytest.param("<p:presentation", _ORDERED_RELS, id="malformed-presentation-xml"),
        pytest.param(
            _ORDERED_PRESENTATION.format(rel_id="rId1"), "<Relationships", id="malformed-rels-xml"
        ),
    ],
)
def test_pptx_monthly_return_rows_reject_unresolvable_slide_order(
    presentation: str, rels: str | None
) -> None:
    content = _ordered_deck(presentation=presentation, rels=rels)

    with pytest.raises(UnsupportedDocumentFormatError, match="only supports PPTX bytes"):
        PptxPrimaryExtractionProvider().monthly_return_rows("doc_bad_order", content)

    assert read_pptx_monthly_return_rows("doc_bad_order", content) is None
