"""Visual artifact extraction for PDF and PPTX sources."""

from __future__ import annotations

import binascii
import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

from inv_man_intake.images.models import ArtifactSource, ImageGeometry, VisualArtifact
from inv_man_intake.images.png import PngEncodeError, rebuild_flate_raster_to_png

_PDF_OBJECT_PATTERN = re.compile(rb"(\d+)\s+\d+\s+obj(.*?)endobj", re.DOTALL)
_PDF_STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_PDF_XOBJECT_REF_PATTERN = re.compile(rb"/(?:Im|Img)\w*\s+(\d+)\s+0\s+R")
_PDF_COLORSPACE_PATTERN = re.compile(rb"/ColorSpace\s*(\[[^\]]*\]|/\w+|\d+\s+\d+\s+R)")
_PDF_DECODEPARMS_PATTERN = re.compile(rb"/DecodeParms\s*<<(.*?)>>", re.DOTALL)
_PDF_HEX_STRING_PATTERN = re.compile(rb"<([0-9A-Fa-f\s]*)>")
_PDF_INDIRECT_REF_PATTERN = re.compile(rb"(\d+)\s+\d+\s+R")

UNSUPPORTED_COLORSPACE = "unsupported_colorspace"
UNSUPPORTED_ENCODING = "unsupported_encoding"

_OCTET_STREAM = "application/octet-stream"

_EXTENSION_BY_MIME = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/jp2": "jp2",
}


class UnsupportedVisualSourceError(ValueError):
    """Raised when visual extraction is requested for an unsupported file type."""


@dataclass(frozen=True)
class _DecodedImage:
    """Decode outcome for one PDF image XObject."""

    mime_type: str
    content: bytes
    geometry: ImageGeometry
    unsupported_reason: str | None = None

    @property
    def extension(self) -> str:
        return _EXTENSION_BY_MIME.get(self.mime_type, "bin")


def extract_visual_artifacts(
    *,
    source_doc_id: str,
    file_name: str,
    content: bytes,
) -> tuple[VisualArtifact, ...]:
    """Extract visual artifacts from PDF/PPTX bytes with stable IDs and hashes."""

    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_artifacts(source_doc_id=source_doc_id, content=content)
    if suffix == ".pptx":
        return _extract_pptx_artifacts(source_doc_id=source_doc_id, content=content)
    raise UnsupportedVisualSourceError(f"unsupported visual source type: {suffix or '<none>'}")


def _extract_pdf_artifacts(*, source_doc_id: str, content: bytes) -> tuple[VisualArtifact, ...]:
    objects = _parse_pdf_objects(content)
    image_streams: dict[int, bytes] = {}
    for object_id, body in objects.items():
        if b"/Subtype /Image" not in body:
            continue
        stream = _extract_pdf_stream(body)
        if stream is None:
            continue
        image_streams[object_id] = stream
    if not image_streams:
        return ()

    page_to_refs = _map_pdf_page_refs(objects)
    artifacts: list[VisualArtifact] = []

    # Preserve page order first, then image reference order for deterministic output.
    for page_number in sorted(page_to_refs):
        seen_refs: set[int] = set()
        for object_id in page_to_refs[page_number]:
            if object_id in seen_refs:
                continue
            seen_refs.add(object_id)
            stream = image_streams.get(object_id)
            if stream is None:
                continue
            decoded = _decode_pdf_image(objects, objects[object_id], stream)
            source = ArtifactSource(
                source_doc_id=source_doc_id,
                page_number=page_number,
                source_ref=f"pdf-object-{object_id}",
            )
            artifacts.append(
                _build_artifact(
                    source=source,
                    mime_type=decoded.mime_type,
                    content=decoded.content,
                    storage_path=(
                        f"artifacts/{source_doc_id}/pdf/page-{page_number}/"
                        f"object-{object_id}.{decoded.extension}"
                    ),
                    geometry=decoded.geometry,
                    unsupported_reason=decoded.unsupported_reason,
                )
            )

    # Fallback for image objects that could not be linked to page-level XObject refs.
    linked_refs = {
        int(source_ref.removeprefix("pdf-object-"))
        for artifact in artifacts
        for source_ref in [artifact.source.source_ref]
        if source_ref is not None and source_ref.startswith("pdf-object-")
    }
    for object_id in sorted(image_streams):
        if object_id in linked_refs:
            continue
        stream = image_streams[object_id]
        decoded = _decode_pdf_image(objects, objects[object_id], stream)
        source = ArtifactSource(
            source_doc_id=source_doc_id,
            page_number=0,
            source_ref=f"pdf-object-{object_id}",
        )
        artifacts.append(
            _build_artifact(
                source=source,
                mime_type=decoded.mime_type,
                content=decoded.content,
                storage_path=(
                    f"artifacts/{source_doc_id}/pdf/page-0/object-{object_id}.{decoded.extension}"
                ),
                geometry=decoded.geometry,
                unsupported_reason=decoded.unsupported_reason,
            )
        )

    return tuple(artifacts)


def _extract_pptx_artifacts(*, source_doc_id: str, content: bytes) -> tuple[VisualArtifact, ...]:
    artifacts: list[VisualArtifact] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        slide_targets = _collect_slide_targets(archive)

        for slide_number in sorted(slide_targets):
            for source_ref, media_path in sorted(slide_targets[slide_number]):
                if media_path not in archive.namelist():
                    continue
                payload = archive.read(media_path)
                extension = Path(media_path).suffix.lower().removeprefix(".")
                mime_type = _mime_from_extension(extension)
                source = ArtifactSource(
                    source_doc_id=source_doc_id,
                    slide_number=slide_number,
                    source_ref=source_ref,
                )
                artifacts.append(
                    _build_artifact(
                        source=source,
                        mime_type=mime_type,
                        content=payload,
                        storage_path=(
                            f"artifacts/{source_doc_id}/pptx/slide-{slide_number}/"
                            f"{Path(media_path).name}"
                        ),
                    )
                )

    return tuple(artifacts)


def _parse_pdf_objects(content: bytes) -> dict[int, bytes]:
    objects: dict[int, bytes] = {}
    for match in _PDF_OBJECT_PATTERN.finditer(content):
        object_id = int(match.group(1))
        objects[object_id] = match.group(2)
    return objects


def _extract_pdf_stream(object_body: bytes) -> bytes | None:
    match = _PDF_STREAM_PATTERN.search(object_body)
    if match is None:
        return None
    stream = match.group(1)
    return stream or None


def _map_pdf_page_refs(objects: dict[int, bytes]) -> dict[int, tuple[int, ...]]:
    page_to_refs: dict[int, tuple[int, ...]] = {}
    page_number = 0
    for _, body in sorted(objects.items()):
        if b"/Type /Page" not in body:
            continue
        page_number += 1
        refs = tuple(int(ref) for ref in _PDF_XOBJECT_REF_PATTERN.findall(body))
        page_to_refs[page_number] = refs
    return page_to_refs


def _pdf_int(object_body: bytes, key: bytes) -> int | None:
    match = re.search(rb"/" + key + rb"\s+(\d+)", object_body)
    return int(match.group(1)) if match else None


def _pdf_filter_name(object_body: bytes) -> str | None:
    for candidate in ("DCTDecode", "JPXDecode", "FlateDecode"):
        if b"/" + candidate.encode() in object_body:
            return candidate
    return None


def _resolve_indirect(objects: dict[int, bytes], value: bytes) -> bytes | None:
    match = _PDF_INDIRECT_REF_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    return objects.get(int(match.group(1)))


def _icc_components(objects: dict[int, bytes], colorspace: bytes) -> int | None:
    """Read ``/N`` from an ``/ICCBased`` stream, which holds the channel count."""

    ref = _PDF_INDIRECT_REF_PATTERN.search(colorspace)
    if ref is None:
        return _pdf_int(colorspace, b"N")
    referenced = objects.get(int(ref.group(1)))
    if referenced is None:
        return None
    return _pdf_int(referenced, b"N")


def _indexed_palette(objects: dict[int, bytes], colorspace: bytes) -> bytes | None:
    hex_match = _PDF_HEX_STRING_PATTERN.search(colorspace)
    if hex_match is not None:
        digits = re.sub(rb"\s", b"", hex_match.group(1))
        if len(digits) % 2:
            digits += b"0"
        try:
            return binascii.unhexlify(digits)
        except binascii.Error:
            return None
    # Otherwise the lookup table is the last indirect reference in the array.
    refs = _PDF_INDIRECT_REF_PATTERN.findall(colorspace)
    if not refs:
        return None
    referenced = objects.get(int(refs[-1]))
    if referenced is None:
        return None
    stream = _extract_pdf_stream(referenced)
    if stream is None:
        return None
    if b"/FlateDecode" in referenced:
        try:
            return zlib.decompress(stream)
        except zlib.error:
            return None
    return stream


def _pdf_colorspace(
    objects: dict[int, bytes], object_body: bytes
) -> tuple[str | None, int | None, bytes | None]:
    """Return the normalized colour space name, channel count, and palette."""

    match = _PDF_COLORSPACE_PATTERN.search(object_body)
    if match is None:
        return None, None, None
    value = match.group(1)
    resolved = _resolve_indirect(objects, value)
    if resolved is not None:
        value = resolved

    if b"/Indexed" in value:
        # PNG PLTE requires 3 bytes/entry; only DeviceRGB bases map cleanly.
        if b"/DeviceRGB" not in value:
            return None, None, None
        return "Indexed", 1, _indexed_palette(objects, value)
    if b"/DeviceCMYK" in value:
        return "DeviceCMYK", 4, None
    if b"/ICCBased" in value:
        return "ICCBased", _icc_components(objects, value), None
    if b"/DeviceRGB" in value:
        return "DeviceRGB", 3, None
    if b"/DeviceGray" in value or b"/CalGray" in value:
        return "DeviceGray", 1, None
    if b"/CalRGB" in value:
        return "CalRGB", 3, None
    if b"/Lab" in value:
        # Lab samples are not RGB; do not silently mis-map into PNG RGB channels.
        return None, None, None
    return None, None, None


def _pdf_geometry(objects: dict[int, bytes], object_body: bytes) -> ImageGeometry:
    color_space, components, palette = _pdf_colorspace(objects, object_body)
    decode_parms = _PDF_DECODEPARMS_PATTERN.search(object_body)
    parms = decode_parms.group(1) if decode_parms else b""
    return ImageGeometry(
        width=_pdf_int(object_body, b"Width"),
        height=_pdf_int(object_body, b"Height"),
        bits_per_component=_pdf_int(object_body, b"BitsPerComponent"),
        color_space=color_space,
        color_components=components,
        filter_name=_pdf_filter_name(object_body),
        predictor=_pdf_int(parms, b"Predictor"),
        predictor_colors=_pdf_int(parms, b"Colors"),
        predictor_columns=_pdf_int(parms, b"Columns"),
        palette=palette,
        has_smask=b"/SMask" in object_body,
    )


def _decode_pdf_image(
    objects: dict[int, bytes], object_body: bytes, stream: bytes
) -> _DecodedImage:
    """Turn one image XObject into viewable bytes, or an explicit skip reason.

    Anything that cannot be decoded keeps the opaque ``.bin`` mime type so a
    skip row is recorded instead of garbage bytes under an image extension.
    """

    geometry = _pdf_geometry(objects, object_body)

    if geometry.color_space == "DeviceCMYK":
        return _DecodedImage(_OCTET_STREAM, stream, geometry, UNSUPPORTED_COLORSPACE)
    if geometry.filter_name == "JPXDecode":
        return _DecodedImage("image/jp2", stream, geometry, UNSUPPORTED_ENCODING)
    if geometry.filter_name == "DCTDecode":
        # A /DCTDecode stream is already a JPEG file; copy it byte-for-byte.
        return _DecodedImage("image/jpeg", stream, geometry)
    if geometry.filter_name == "FlateDecode":
        try:
            return _DecodedImage(
                "image/png", rebuild_flate_raster_to_png(stream, geometry), geometry
            )
        except PngEncodeError:
            return _DecodedImage(_OCTET_STREAM, stream, geometry, UNSUPPORTED_ENCODING)

    return _DecodedImage(_OCTET_STREAM, stream, geometry, UNSUPPORTED_ENCODING)


def _collect_slide_targets(archive: zipfile.ZipFile) -> dict[int, tuple[tuple[str, str], ...]]:
    by_slide: dict[int, tuple[tuple[str, str], ...]] = {}
    slide_rels = sorted(
        path
        for path in archive.namelist()
        if path.startswith("ppt/slides/_rels/") and path.endswith(".xml.rels")
    )
    for rel_path in slide_rels:
        slide_number = _slide_number(rel_path)
        if slide_number is None:
            continue
        root = ET.fromstring(archive.read(rel_path))
        entries: list[tuple[str, str]] = []
        for rel in root:
            rel_type = rel.attrib.get("Type", "")
            if not rel_type.endswith("/image"):
                continue
            source_ref = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            resolved = _resolve_slide_target(target)
            entries.append((source_ref, resolved))
        by_slide[slide_number] = tuple(entries)
    return by_slide


def _slide_number(rel_path: str) -> int | None:
    match = re.search(r"slide(\d+)\.xml\.rels$", rel_path)
    if match is None:
        return None
    return int(match.group(1))


def _resolve_slide_target(target: str) -> str:
    normalized = target.replace("\\", "/")
    while normalized.startswith("../"):
        normalized = normalized.removeprefix("../")
    return f"ppt/{normalized}"


def _mime_from_extension(extension: str) -> str:
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tif": "image/tiff",
        "tiff": "image/tiff",
        "svg": "image/svg+xml",
    }.get(extension, "application/octet-stream")


def _build_artifact(
    *,
    source: ArtifactSource,
    mime_type: str,
    content: bytes,
    storage_path: str,
    geometry: ImageGeometry | None = None,
    unsupported_reason: str | None = None,
) -> VisualArtifact:
    digest = hashlib.sha256(content).hexdigest()
    source_key = (
        f"p{source.page_number}" if source.page_number is not None else f"s{source.slide_number}"
    )
    reference_key = source.source_ref or "none"
    artifact_seed = f"{source.source_doc_id}|{source_key}|{reference_key}|{digest}".encode()
    artifact_id = f"va_{hashlib.sha1(artifact_seed).hexdigest()[:16]}"
    return VisualArtifact(
        artifact_id=artifact_id,
        source=source,
        mime_type=mime_type,
        sha256=digest,
        byte_size=len(content),
        storage_path=storage_path,
        content=content,
        geometry=geometry,
        unsupported_reason=unsupported_reason,
    )
