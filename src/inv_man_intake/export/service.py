"""Swappable export service port with a deterministic manifest boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from inv_man_intake.export.manifest import ExportItem, ExportManifest


@runtime_checkable
class Exporter(Protocol):
    """Backend which materializes export results into a complete manifest."""

    @property
    def name(self) -> str: ...

    def export(self, items: tuple[ExportItem, ...]) -> ExportManifest:
        """Return every produced item and every intentional skip."""


@runtime_checkable
class ExportService(Protocol):
    """Stable consumer-facing port for user-deliverable exports."""

    @property
    def backend_name(self) -> str: ...

    def export(self, items: tuple[ExportItem, ...]) -> ExportManifest:
        """Materialize an export manifest through the selected backend."""


@dataclass(frozen=True)
class ManifestExporter:
    """Default local backend: normalize exporter results without egress or I/O."""

    exporter_name: str = "manifest-local"

    @property
    def name(self) -> str:
        return self.exporter_name

    def export(self, items: tuple[ExportItem, ...]) -> ExportManifest:
        return ExportManifest.from_items(items)


@dataclass(frozen=True)
class DefaultExportService:
    """Concrete service that delegates the export boundary to one backend."""

    backend: Exporter

    @property
    def backend_name(self) -> str:
        return self.backend.name

    def export(self, items: tuple[ExportItem, ...]) -> ExportManifest:
        return self.backend.export(items)


def ensure_export_service(candidate: object) -> ExportService:
    """Validate an export service at the consumer boundary."""

    if isinstance(candidate, ExportService):
        return candidate
    raise TypeError("expected an ExportService")


def build_default_export_service() -> ExportService:
    """Build the current no-egress default export service."""

    return DefaultExportService(backend=ManifestExporter())


__all__ = [
    "DefaultExportService",
    "ExportService",
    "Exporter",
    "ManifestExporter",
    "build_default_export_service",
    "ensure_export_service",
]
