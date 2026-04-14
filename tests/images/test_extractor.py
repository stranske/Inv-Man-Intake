"""Tests for PDF/PPTX visual artifact extraction."""

from __future__ import annotations

import io
import zipfile

import pytest

from inv_man_intake.images.extractor import UnsupportedVisualSourceError, extract_visual_artifacts


def _pdf_fixture_bytes() -> bytes:
    return (
        b"1 0 obj\n<< /Type /Page /Resources << /XObject << /Im0 5 0 R >> >> >>\nendobj\n"
        b"2 0 obj\n<< /Type /Page /Resources << /XObject << /Im1 6 0 R >> >> >>\nendobj\n"
        b"5 0 obj\n<< /Subtype /Image /Filter /DCTDecode /Length 3 >>\n"
        b"stream\nabc\nendstream\nendobj\n"
        b"6 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Length 3 >>\n"
        b"stream\ndef\nendstream\nendobj\n"
    )


def _pptx_fixture_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "ppt/slides/_rels/slide1.xml.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId2" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                'Target="../media/image1.png"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "ppt/slides/_rels/slide2.xml.rels",
            (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId9" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                'Target="../media/image2.jpg"/>'
                "</Relationships>"
            ),
        )
        archive.writestr("ppt/media/image1.png", b"png-payload")
        archive.writestr("ppt/media/image2.jpg", b"jpg-payload")
    return buffer.getvalue()


def test_extract_visual_artifacts_from_pdf_links_page_and_hash_metadata() -> None:
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_pdf_1",
        file_name="manager_deck.pdf",
        content=_pdf_fixture_bytes(),
    )

    assert len(artifacts) == 2
    assert artifacts[0].source.page_number == 1
    assert artifacts[0].source.source_ref == "pdf-object-5"
    assert artifacts[0].mime_type == "image/jpeg"
    assert artifacts[0].sha256
    assert artifacts[0].artifact_id.startswith("va_")
    assert artifacts[1].source.page_number == 2
    assert artifacts[1].mime_type == "application/octet-stream"


def test_extract_visual_artifacts_from_pptx_links_slide_and_relationship_metadata() -> None:
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_pptx_1",
        file_name="manager_update.pptx",
        content=_pptx_fixture_bytes(),
    )

    assert len(artifacts) == 2
    assert artifacts[0].source.slide_number == 1
    assert artifacts[0].source.source_ref == "rId2"
    assert artifacts[0].mime_type == "image/png"
    assert artifacts[1].source.slide_number == 2
    assert artifacts[1].source.source_ref == "rId9"
    assert artifacts[1].mime_type == "image/jpeg"


def test_visual_artifact_ids_are_stable_for_same_source_payload() -> None:
    first = extract_visual_artifacts(
        source_doc_id="doc_pdf_2",
        file_name="deck.pdf",
        content=_pdf_fixture_bytes(),
    )
    second = extract_visual_artifacts(
        source_doc_id="doc_pdf_2",
        file_name="deck.pdf",
        content=_pdf_fixture_bytes(),
    )

    assert [item.artifact_id for item in first] == [item.artifact_id for item in second]
    assert [item.sha256 for item in first] == [item.sha256 for item in second]


def test_extract_visual_artifacts_skips_pdf_image_objects_without_stream_bytes() -> None:
    content = (
        b"1 0 obj\n<< /Type /Page /Resources << /XObject << /Im0 5 0 R >> >> >>\nendobj\n"
        b"5 0 obj\n<< /Subtype /Image /Filter /DCTDecode /Length 0 >>\nendobj\n"
    )

    artifacts = extract_visual_artifacts(
        source_doc_id="doc_pdf_empty",
        file_name="manager_deck.pdf",
        content=content,
    )

    assert artifacts == ()


def test_extract_visual_artifacts_rejects_unsupported_extension() -> None:
    with pytest.raises(UnsupportedVisualSourceError, match="unsupported visual source type"):
        extract_visual_artifacts(source_doc_id="doc_1", file_name="notes.txt", content=b"x")
