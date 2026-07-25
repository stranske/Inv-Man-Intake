"""Deterministic manifest contracts for user-facing exports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ExportSkipReason = Literal[
    "unsupported_colorspace",
    "unsupported_encoding",
    "vector_render_failed",
    "no_table_found",
    "no_series_found",
]


@dataclass(frozen=True)
class ExportArtifact:
    """One materialized export together with its source lineage references."""

    name: str
    media_type: str
    content: bytes
    provenance_refs: tuple[str, ...]


@dataclass(frozen=True)
class ManifestArtifact:
    """Associate a produced artifact with the input item it represents."""

    item_ref: str
    artifact: ExportArtifact


@dataclass(frozen=True)
class ManifestSkip:
    """Describe an intentionally omitted export item without losing its reason."""

    item_ref: str
    reason_code: ExportSkipReason


@dataclass(frozen=True)
class ExportItem:
    """One exporter result, which is either materialized or explicitly skipped."""

    item_ref: str
    artifact: ExportArtifact | None = None
    skip_reason: ExportSkipReason | None = None

    def __post_init__(self) -> None:
        if (self.artifact is None) == (self.skip_reason is None):
            raise ValueError("an export item must contain exactly one artifact or skip reason")


@dataclass(frozen=True)
class ExportManifest:
    """A stable, complete record of produced and intentionally skipped exports."""

    artifacts: tuple[ManifestArtifact, ...]
    skipped: tuple[ManifestSkip, ...]

    @classmethod
    def from_items(cls, items: tuple[ExportItem, ...]) -> ExportManifest:
        """Build a deterministic manifest, rejecting duplicate input references."""

        item_refs = [item.item_ref for item in items]
        if len(item_refs) != len(set(item_refs)):
            raise ValueError("export item references must be unique")

        artifacts = tuple(
            sorted(
                (
                    ManifestArtifact(item_ref=item.item_ref, artifact=item.artifact)
                    for item in items
                    if item.artifact is not None
                ),
                key=lambda entry: entry.item_ref,
            )
        )
        skipped = tuple(
            sorted(
                (
                    ManifestSkip(item_ref=item.item_ref, reason_code=item.skip_reason)
                    for item in items
                    if item.skip_reason is not None
                ),
                key=lambda entry: entry.item_ref,
            )
        )
        return cls(artifacts=artifacts, skipped=skipped)
