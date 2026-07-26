"""Tests for rebuilding PDF image XObjects into real, viewable export files."""

from __future__ import annotations

import struct
import zlib

from inv_man_intake.export.image_export import (
    build_image_export_items,
    export_document_images,
)
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult
from inv_man_intake.images.extractor import extract_visual_artifacts
from inv_man_intake.intake.standard_elements import (
    StandardElementLibrary,
    load_standard_element_library,
)
from inv_man_intake.packet import PacketFile, ingest_packet

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class _StubProvider:
    """Minimal extraction provider: this suite exercises the image path only."""

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        _ = content
        return ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            provider_name="stub",
            fields=(),
        )


def _library() -> StandardElementLibrary:
    return load_standard_element_library(
        {
            "version": "image-export-test",
            "non_authoritative": True,
            "doc_types": {
                "deck": [
                    {
                        "key": "operations.aum",
                        "detector_name": "field_present",
                        "mandatory": False,
                    }
                ]
            },
        }
    )


_WIDTH = 4
_HEIGHT = 3


def _rgb_samples() -> bytes:
    return bytes(
        ((row * _WIDTH + column) * 7) % 256
        for row in range(_HEIGHT)
        for column in range(_WIDTH)
        for _ in range(3)
    )


def _flate_image_object(object_id: int, *, predictor: bool) -> bytes:
    """Build one ``/FlateDecode`` RGB image XObject, optionally PNG-predicted."""

    samples = _rgb_samples()
    stride = _WIDTH * 3
    if predictor:
        payload = b"".join(
            b"\x00" + samples[row * stride : (row + 1) * stride] for row in range(_HEIGHT)
        )
        decode_parms = (
            b" /DecodeParms << /Predictor 15 /Colors 3 /Columns "
            + str(_WIDTH).encode()
            + b" /BitsPerComponent 8 >>"
        )
    else:
        payload = samples
        decode_parms = b""

    stream = zlib.compress(payload)
    return (
        str(object_id).encode()
        + b" 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width "
        + str(_WIDTH).encode()
        + b" /Height "
        + str(_HEIGHT).encode()
        + b" /BitsPerComponent 8 /ColorSpace /DeviceRGB"
        + decode_parms
        + b" >>\nstream\n"
        + stream
        + b"\nendstream\nendobj\n"
    )


def _cmyk_image_object(object_id: int) -> bytes:
    return (
        str(object_id).encode()
        + b" 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace /DeviceCMYK >>\nstream\n"
        + zlib.compress(bytes(range(16)))
        + b"\nendstream\nendobj\n"
    )


def _pdf_with(*objects: bytes, page_refs: str) -> bytes:
    page = (
        b"1 0 obj\n<< /Type /Page /Resources << /XObject << "
        + page_refs.encode()
        + b" >> >> >>\nendobj\n"
    )
    return page + b"".join(objects)


def _flate_deck(*, predictor: bool = True) -> bytes:
    return _pdf_with(_flate_image_object(5, predictor=predictor), page_refs="/Im0 5 0 R")


def _png_ihdr(png: bytes) -> tuple[int, int, int, int]:
    width, height, bit_depth, color_type = struct.unpack(">IIBB", png[16:26])
    return width, height, bit_depth, color_type


def _png_idat(png: bytes) -> bytes:
    offset = len(PNG_MAGIC)
    chunks: list[bytes] = []
    while offset < len(png):
        (length,) = struct.unpack(">I", png[offset : offset + 4])
        tag = png[offset + 4 : offset + 8]
        if tag == b"IDAT":
            chunks.append(png[offset + 8 : offset + 8 + length])
        offset += 12 + length
    return zlib.decompress(b"".join(chunks))


def test_flate_raster_rebuilds_to_valid_png() -> None:
    manifest = export_document_images(
        source_doc_id="doc_flate",
        file_name="deck.pdf",
        content=_flate_deck(),
    )

    assert len(manifest.artifacts) == 1
    assert manifest.skipped == ()

    png = manifest.artifacts[0].artifact.content
    assert png.startswith(PNG_MAGIC)
    assert manifest.artifacts[0].artifact.media_type == "image/png"
    assert manifest.artifacts[0].artifact.name.endswith(".png")

    width, height, bit_depth, color_type = _png_ihdr(png)
    assert (width, height) == (_WIDTH, _HEIGHT)
    assert (bit_depth, color_type) == (8, 2)

    # One filter byte plus width*3 sample bytes for each scanline.
    assert len(_png_idat(png)) == (_WIDTH * 3 + 1) * _HEIGHT


def test_unpredicted_flate_raster_gains_png_filter_bytes() -> None:
    manifest = export_document_images(
        source_doc_id="doc_raw",
        file_name="deck.pdf",
        content=_flate_deck(predictor=False),
    )

    png = manifest.artifacts[0].artifact.content
    scanlines = _png_idat(png)
    stride = _WIDTH * 3 + 1
    assert png.startswith(PNG_MAGIC)
    assert all(scanlines[row * stride] == 0 for row in range(_HEIGHT))
    assert scanlines[1:stride] == _rgb_samples()[: _WIDTH * 3]


def test_cmyk_is_reported_unsupported_and_not_emitted() -> None:
    manifest = export_document_images(
        source_doc_id="doc_cmyk",
        file_name="deck.pdf",
        content=_pdf_with(_cmyk_image_object(5), page_refs="/Im0 5 0 R"),
    )

    assert manifest.artifacts == ()
    assert len(manifest.skipped) == 1
    assert manifest.skipped[0].reason_code == "unsupported_colorspace"
    assert manifest.skipped[0].item_ref == "doc_cmyk:image:0"


def test_jpx_encoding_is_reported_unsupported() -> None:
    jpx = (
        b"5 0 obj\n<< /Subtype /Image /Filter /JPXDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace /DeviceRGB >>\nstream\njp2-bytes\nendstream\nendobj\n"
    )
    manifest = export_document_images(
        source_doc_id="doc_jpx",
        file_name="deck.pdf",
        content=_pdf_with(jpx, page_refs="/Im0 5 0 R"),
    )

    assert manifest.artifacts == ()
    assert [entry.reason_code for entry in manifest.skipped] == ["unsupported_encoding"]


def test_dct_stream_is_exported_byte_for_byte_as_jpeg() -> None:
    jpeg_bytes = b"\xff\xd8\xff\xe0jpeg-payload\xff\xd9"
    dct = (
        b"5 0 obj\n<< /Subtype /Image /Filter /DCTDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace /DeviceRGB >>\nstream\n"
        + jpeg_bytes
        + b"\nendstream\nendobj\n"
    )
    manifest = export_document_images(
        source_doc_id="doc_jpeg",
        file_name="deck.pdf",
        content=_pdf_with(dct, page_refs="/Im0 5 0 R"),
    )

    assert len(manifest.artifacts) == 1
    artifact = manifest.artifacts[0].artifact
    assert artifact.content == jpeg_bytes
    assert artifact.media_type == "image/jpeg"
    assert artifact.name.endswith(".jpg")


def test_indexed_colorspace_emits_palette_png() -> None:
    palette = b"\xff\x00\x00\x00\xff\x00"
    indexed = (
        b"5 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace [/Indexed /DeviceRGB 1 <FF0000 00FF00>]"
        b" >>\nstream\n" + zlib.compress(bytes([0, 1, 1, 0])) + b"\nendstream\nendobj\n"
    )
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_indexed",
        file_name="deck.pdf",
        content=_pdf_with(indexed, page_refs="/Im0 5 0 R"),
    )

    assert artifacts[0].mime_type == "image/png"
    assert artifacts[0].geometry is not None
    assert artifacts[0].geometry.palette == palette
    assert b"PLTE" in artifacts[0].content
    assert _png_ihdr(artifacts[0].content)[3] == 3


def test_device_gray_rebuilds_as_grayscale_png() -> None:
    gray = (
        b"5 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace /DeviceGray >>\nstream\n"
        + zlib.compress(bytes([0, 64, 128, 255]))
        + b"\nendstream\nendobj\n"
    )
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_gray",
        file_name="deck.pdf",
        content=_pdf_with(gray, page_refs="/Im0 5 0 R"),
    )

    assert artifacts[0].mime_type == "image/png"
    assert _png_ihdr(artifacts[0].content) == (2, 2, 8, 0)


def test_iccbased_channel_count_comes_from_the_profile_stream() -> None:
    icc = (
        b"5 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace [/ICCBased 7 0 R] >>\nstream\n"
        + zlib.compress(bytes(range(12)))
        + b"\nendstream\nendobj\n"
        b"7 0 obj\n<< /N 3 /Alternate /DeviceRGB >>\nstream\nicc\nendstream\nendobj\n"
    )
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_icc",
        file_name="deck.pdf",
        content=_pdf_with(icc, page_refs="/Im0 5 0 R"),
    )

    geometry = artifacts[0].geometry
    assert geometry is not None
    assert geometry.color_space == "ICCBased"
    assert geometry.color_components == 3
    assert _png_ihdr(artifacts[0].content) == (2, 2, 8, 2)


def test_smask_presence_is_retained_on_the_artifact() -> None:
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_smask",
        file_name="deck.pdf",
        content=_pdf_with(
            b"5 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width 2 /Height 2"
            b" /BitsPerComponent 8 /ColorSpace /DeviceGray /SMask 9 0 R >>\nstream\n"
            + zlib.compress(bytes([1, 2, 3, 4]))
            + b"\nendstream\nendobj\n",
            page_refs="/Im0 5 0 R",
        ),
    )

    geometry = artifacts[0].geometry
    assert geometry is not None
    assert geometry.has_smask is True


def test_extractor_retains_xobject_geometry() -> None:
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_geom",
        file_name="deck.pdf",
        content=_flate_deck(),
    )

    geometry = artifacts[0].geometry
    assert geometry is not None
    assert (geometry.width, geometry.height) == (_WIDTH, _HEIGHT)
    assert geometry.bits_per_component == 8
    assert geometry.color_space == "DeviceRGB"
    assert geometry.color_components == 3
    assert geometry.predictor == 15
    assert geometry.filter_name == "FlateDecode"


def test_export_items_carry_stable_provenance_refs() -> None:
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_prov",
        file_name="deck.pdf",
        content=_flate_deck(),
    )
    items = build_image_export_items(artifacts, source_doc_id="doc_prov")

    assert [item.item_ref for item in items] == ["doc_prov:image:0"]
    assert items[0].artifact is not None
    assert items[0].artifact.provenance_refs[0] == "doc_prov:image:0"


def test_packet_exposes_real_image_bytes_not_ref_strings() -> None:
    profile = ingest_packet(
        [PacketFile(document_id="doc_flate", content=_flate_deck(), filename="deck.pdf")],
        provider=_StubProvider(),
        standard_library=_library(),
    )

    assert profile.graphics_refs == ("doc_flate:image:0",)
    assert len(profile.graphics_artifacts) == 1
    content = profile.graphics_artifacts[0].content
    assert isinstance(content, bytes)
    assert content.startswith(PNG_MAGIC)
    assert not isinstance(content, str)


def test_packet_records_unsupported_images_as_skips() -> None:
    profile = ingest_packet(
        [
            PacketFile(
                document_id="doc_cmyk",
                content=_pdf_with(_cmyk_image_object(5), page_refs="/Im0 5 0 R"),
                filename="deck.pdf",
            )
        ],
        provider=_StubProvider(),
        standard_library=_library(),
    )

    assert profile.graphics_refs == ()
    assert profile.graphics_artifacts == ()
    assert profile.graphics_skipped == (("doc_cmyk:image:0", "unsupported_colorspace"),)


def test_non_visual_document_yields_empty_manifest() -> None:
    manifest = export_document_images(
        source_doc_id="doc_txt",
        file_name="notes.txt",
        content=b"plain text",
    )

    assert manifest.artifacts == ()
    assert manifest.skipped == ()


def test_indexed_non_rgb_base_is_unsupported() -> None:
    indexed_gray = (
        b"5 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace [/Indexed /DeviceGray 1 <00 FF>]"
        b" >>\nstream\n" + zlib.compress(bytes([0, 1, 1, 0])) + b"\nendstream\nendobj\n"
    )
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_indexed_gray",
        file_name="deck.pdf",
        content=_pdf_with(indexed_gray, page_refs="/Im0 5 0 R"),
    )

    assert artifacts[0].mime_type == "application/octet-stream"
    assert artifacts[0].unsupported_reason == "unsupported_encoding"


def test_lab_colorspace_is_unsupported_not_mapped_to_rgb() -> None:
    lab = (
        b"5 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace /Lab >>\nstream\n"
        + zlib.compress(bytes(range(12)))
        + b"\nendstream\nendobj\n"
    )
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_lab",
        file_name="deck.pdf",
        content=_pdf_with(lab, page_refs="/Im0 5 0 R"),
    )

    assert artifacts[0].mime_type == "application/octet-stream"
    assert artifacts[0].unsupported_reason == "unsupported_encoding"
    assert artifacts[0].geometry is not None
    assert artifacts[0].geometry.color_space is None


def test_tiff_predictor_is_rejected_instead_of_silent_misdecode() -> None:
    predicted = (
        b"5 0 obj\n<< /Subtype /Image /Filter /FlateDecode /Width 2 /Height 2"
        b" /BitsPerComponent 8 /ColorSpace /DeviceRGB"
        b" /DecodeParms << /Predictor 2 /Colors 3 /Columns 2 >> >>\nstream\n"
        + zlib.compress(bytes(range(12)))
        + b"\nendstream\nendobj\n"
    )
    artifacts = extract_visual_artifacts(
        source_doc_id="doc_pred2",
        file_name="deck.pdf",
        content=_pdf_with(predicted, page_refs="/Im0 5 0 R"),
    )

    assert artifacts[0].mime_type == "application/octet-stream"
    assert artifacts[0].unsupported_reason == "unsupported_encoding"


def test_packet_isolates_graphics_export_failures_per_document(monkeypatch) -> None:
    from inv_man_intake import packet as packet_mod

    good = PacketFile(document_id="doc_ok", content=_flate_deck(), filename="ok.pdf")
    bad = PacketFile(document_id="doc_bad", content=_flate_deck(), filename="bad.pdf")
    original = packet_mod.export_document_images

    def _flaky_export(*, source_doc_id: str, file_name: str | None, content: bytes):
        if source_doc_id == "doc_bad":
            raise RuntimeError("simulated decode failure")
        return original(source_doc_id=source_doc_id, file_name=file_name, content=content)

    monkeypatch.setattr(packet_mod, "export_document_images", _flaky_export)

    profile = ingest_packet(
        [good, bad],
        provider=_StubProvider(),
        standard_library=_library(),
    )

    assert profile.graphics_refs == ("doc_ok:image:0",)
    assert len(profile.graphics_artifacts) == 1
    assert profile.graphics_skipped == (("doc_bad:image:0", "unsupported_encoding"),)
