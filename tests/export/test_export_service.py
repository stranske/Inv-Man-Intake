"""Tests for the export service port and deterministic manifest contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from inv_man_intake.export import (
    DefaultExportService,
    ExportArtifact,
    ExportItem,
    ExportManifest,
    ManifestExporter,
    build_default_export_service,
    ensure_export_service,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _items() -> tuple[ExportItem, ...]:
    return (
        ExportItem(
            item_ref="deck:page:2:image:1",
            artifact=ExportArtifact(
                name="page-2-image-1.png",
                media_type="image/png",
                content=b"png-bytes",
                provenance_refs=("deck:page:2", "deck:image:1"),
            ),
        ),
        ExportItem(
            item_ref="deck:page:1:image:3",
            skip_reason="unsupported_colorspace",
        ),
    )


def test_backend_is_swappable() -> None:
    default_service = build_default_export_service()
    fake_service = DefaultExportService(backend=_FakeExporter())

    default_manifest = default_service.export(_items())
    fake_manifest = fake_service.export(_items())

    assert default_manifest == fake_manifest
    assert default_service.backend_name == "manifest-local"
    assert fake_service.backend_name == "fake-exporter"


def test_manifest_records_skipped_items_with_reason_codes() -> None:
    manifest = build_default_export_service().export(_items())

    assert [entry.item_ref for entry in manifest.artifacts] == ["deck:page:2:image:1"]
    assert manifest.artifacts[0].artifact.media_type == "image/png"
    assert manifest.artifacts[0].artifact.provenance_refs == ("deck:page:2", "deck:image:1")
    assert [(entry.item_ref, entry.reason_code) for entry in manifest.skipped] == [
        ("deck:page:1:image:3", "unsupported_colorspace")
    ]


def test_manifest_sorts_by_item_ref_and_rejects_ambiguous_items() -> None:
    manifest = ExportManifest.from_items(
        (
            ExportItem(item_ref="z", skip_reason="no_series_found"),
            ExportItem(item_ref="a", skip_reason="no_table_found"),
        )
    )

    assert [entry.item_ref for entry in manifest.skipped] == ["a", "z"]
    with pytest.raises(ValueError, match="exactly one artifact or skip reason"):
        ExportItem(item_ref="broken")


def test_service_boundary_rejects_a_concrete_backend() -> None:
    assert ensure_export_service(build_default_export_service()).backend_name == "manifest-local"
    with pytest.raises(TypeError, match="ExportService"):
        ensure_export_service(ManifestExporter())


def test_consumers_do_not_import_concrete_exporters_directly() -> None:
    consumer_sources = (
        _REPO_ROOT / "src/inv_man_intake/packet.py",
        _REPO_ROOT / "src/inv_man_intake/run.py",
    )
    banned_tokens = (
        "ManifestExporter",
        "from inv_man_intake.export.service import ManifestExporter",
    )

    for source_path in consumer_sources:
        source = source_path.read_text()
        assert not any(token in source for token in banned_tokens), source_path


class _FakeExporter:
    @property
    def name(self) -> str:
        return "fake-exporter"

    def export(self, items: tuple[ExportItem, ...]) -> ExportManifest:
        return ExportManifest.from_items(items)
