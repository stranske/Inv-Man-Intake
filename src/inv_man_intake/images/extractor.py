"""Visual artifact extraction for PDF and PPTX sources."""

from __future__ import annotations

import hashlib
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from inv_man_intake.images.models import ArtifactSource, VisualArtifact

_PDF_OBJECT_PATTERN = re.compile(rb"(\d+)\s+\d+\s+obj(.*?)endobj", re.DOTALL)
_PDF_STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_PDF_XOBJECT_REF_PATTERN = re.compile(rb"/(?:Im|Img)\w*\s+(\d+)\s+0\s+R")


class UnsupportedVisualSourceError(ValueError):
    """Raised when visual extraction is requested for an unsupported file type."""


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
    image_streams = {
        object_id: _extract_pdf_stream(body)
        for object_id, body in objects.items()
        if b"/Subtype /Image" in body
    }
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
            mime_type = _pdf_mime_type(objects[object_id])
            source = ArtifactSource(
                source_doc_id=source_doc_id,
                page_number=page_number,
                source_ref=f"pdf-object-{object_id}",
            )
            artifacts.append(
                _build_artifact(
                    source=source,
                    mime_type=mime_type,
                    content=stream,
                    storage_path=(
                        f"artifacts/{source_doc_id}/pdf/page-{page_number}/object-{object_id}.bin"
                    ),
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
        mime_type = _pdf_mime_type(objects[object_id])
        source = ArtifactSource(
            source_doc_id=source_doc_id,
            page_number=0,
            source_ref=f"pdf-object-{object_id}",
        )
        artifacts.append(
            _build_artifact(
                source=source,
                mime_type=mime_type,
                content=stream,
                storage_path=f"artifacts/{source_doc_id}/pdf/page-0/object-{object_id}.bin",
            )
        )

    return tuple(artifacts)


def _extract_pptx_artifacts(*, source_doc_id: str, content: bytes) -> tuple[VisualArtifact, ...]:
    archive = zipfile.ZipFile(io.BytesIO(content))
    slide_targets = _collect_slide_targets(archive)

    artifacts: list[VisualArtifact] = []
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


def _extract_pdf_stream(object_body: bytes) -> bytes:
    match = _PDF_STREAM_PATTERN.search(object_body)
    if match is None:
        return b""
    return match.group(1)


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


def _pdf_mime_type(object_body: bytes) -> str:
    if b"/DCTDecode" in object_body:
        return "image/jpeg"
    if b"/JPXDecode" in object_body:
        return "image/jp2"
    if b"/FlateDecode" in object_body:
        return "image/png"
    return "application/octet-stream"


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
) -> VisualArtifact:
    digest = hashlib.sha256(content).hexdigest()
    source_key = f"p{source.page_number}" if source.page_number is not None else f"s{source.slide_number}"
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
    )
