"""Map extracted visual artifacts onto the deterministic export manifest."""

from __future__ import annotations

from collections.abc import Sequence

from inv_man_intake.export.manifest import (
    ExportArtifact,
    ExportItem,
    ExportManifest,
    ExportSkipReason,
)
from inv_man_intake.export.service import ExportService, build_default_export_service
from inv_man_intake.images.extractor import (
    UNSUPPORTED_COLORSPACE,
    UNSUPPORTED_ENCODING,
    UnsupportedVisualSourceError,
    extract_visual_artifacts,
)
from inv_man_intake.images.models import VisualArtifact

_SKIP_REASONS: dict[str, ExportSkipReason] = {
    UNSUPPORTED_COLORSPACE: "unsupported_colorspace",
    UNSUPPORTED_ENCODING: "unsupported_encoding",
}

_EXPORTABLE_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/bmp", "image/tiff", "image/svg+xml"}
)


def image_item_ref(source_doc_id: str, index: int) -> str:
    """Stable provenance reference; unchanged so existing consumers keep working."""

    return f"{source_doc_id}:image:{index}"


def build_image_export_items(
    artifacts: Sequence[VisualArtifact],
    *,
    source_doc_id: str,
) -> tuple[ExportItem, ...]:
    """Produce one export item per artifact: real bytes, or an explicit skip."""

    items: list[ExportItem] = []
    for index, artifact in enumerate(artifacts):
        item_ref = image_item_ref(source_doc_id, index)
        skip_reason = _skip_reason_for(artifact)
        if skip_reason is not None:
            items.append(ExportItem(item_ref=item_ref, skip_reason=skip_reason))
            continue
        items.append(
            ExportItem(
                item_ref=item_ref,
                artifact=ExportArtifact(
                    name=artifact.storage_path.rsplit("/", 1)[-1],
                    media_type=artifact.mime_type,
                    content=artifact.content,
                    provenance_refs=(item_ref, artifact.artifact_id),
                ),
            )
        )
    return tuple(items)


def _skip_reason_for(artifact: VisualArtifact) -> ExportSkipReason | None:
    if artifact.unsupported_reason is not None:
        return _SKIP_REASONS.get(artifact.unsupported_reason, "unsupported_encoding")
    if artifact.mime_type not in _EXPORTABLE_MEDIA_TYPES:
        return "unsupported_encoding"
    return None


def export_document_images(
    *,
    source_doc_id: str,
    file_name: str | None,
    content: bytes,
    export_service: ExportService | None = None,
) -> ExportManifest:
    """Extract and export one document's images, or an empty manifest if it has none."""

    if not file_name:
        return ExportManifest(artifacts=(), skipped=())
    try:
        artifacts = extract_visual_artifacts(
            source_doc_id=source_doc_id,
            file_name=file_name,
            content=content,
        )
    except UnsupportedVisualSourceError:
        return ExportManifest(artifacts=(), skipped=())

    service = export_service if export_service is not None else build_default_export_service()
    return service.export(build_image_export_items(artifacts, source_doc_id=source_doc_id))


def merge_manifests(manifests: Sequence[ExportManifest]) -> ExportManifest:
    """Combine per-document manifests, preserving deterministic item ordering."""

    artifacts = tuple(entry for manifest in manifests for entry in manifest.artifacts)
    skipped = tuple(entry for manifest in manifests for entry in manifest.skipped)
    return ExportManifest(artifacts=artifacts, skipped=skipped)


__all__ = [
    "build_image_export_items",
    "export_document_images",
    "image_item_ref",
    "merge_manifests",
]
