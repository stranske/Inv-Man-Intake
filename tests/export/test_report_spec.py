"""Tests for one-pager output-substrate report specifications."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inv_man_intake.export.one_pager import build_one_pager, export_one_pager
from inv_man_intake.export.report_spec import export_one_pager as compatibility_export_one_pager
from inv_man_intake.export.report_spec import validate_report_spec
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.intake.standard_elements import load_standard_element_library
from inv_man_intake.packet import PacketFile, ingest_packet

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "intake" / "pdf_primary_mixed_bundle.json"


class _FixtureProvider:
    @property
    def name(self) -> str:
        return "fixture"

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        _ = content
        return ExtractedDocumentResult(
            source_doc_id,
            self.name,
            (
                ExtractedField(
                    "identity.manager",
                    "Summit Arc Advisors",
                    0.9,
                    source_doc_id,
                    1,
                    "fixture",
                ),
                ExtractedField(
                    "performance.net_return_1y",
                    "12.5%",
                    0.8,
                    source_doc_id,
                    1,
                    "fixture",
                ),
            ),
        )


def _profile():
    library = load_standard_element_library(
        {
            "version": "report-spec-test",
            "non_authoritative": True,
            "doc_types": {
                "deck": [
                    {
                        "key": "identity.manager",
                        "detector_name": "field_present",
                        "mandatory": True,
                    }
                ]
            },
        }
    )
    return ingest_packet(
        (PacketFile("fixture", FIXTURE.read_bytes(), "fixture_deck.json"),),
        provider=_FixtureProvider(),
        standard_library=library,
        packet_id="report-spec-fixture",
    )


def test_report_spec_validates(tmp_path: Path) -> None:
    """The named gate validates the persisted output-substrate producer contract."""

    output_dir = tmp_path / "export"
    one_pager_path, report_spec_path = export_one_pager(
        _profile(),
        output_dir,
        workspace_bundle_ref="workspace.json",
        manifest_ref="artifact:manifest.json",
    )

    assert one_pager_path == output_dir / "one-pager.json"
    assert report_spec_path == output_dir / "report-spec.json"
    persisted = json.loads(report_spec_path.read_text(encoding="utf-8"))
    validate_report_spec(persisted)
    assert persisted == {
        "schema_version": "output-substrate/v1",
        "renderer_profile": "investment_review",
        "workspace_bundle_ref": {"path": "workspace.json"},
        "manifest_ref": "artifact:manifest.json",
        "manifest_csv_exports": [],
    }


def test_report_spec_rejects_missing_renderer_profile(tmp_path: Path) -> None:
    _, report_spec_path = export_one_pager(
        _profile(),
        tmp_path,
        workspace_bundle_ref="workspace.json",
        manifest_ref="artifact:manifest.json",
    )
    payload = json.loads(report_spec_path.read_text(encoding="utf-8"))
    del payload["renderer_profile"]

    with pytest.raises(ValueError, match="missing required field: renderer_profile"):
        validate_report_spec(payload)


def test_export_one_pager_preserves_the_pure_model_payload(tmp_path: Path) -> None:
    profile = _profile()
    one_pager_path, _ = export_one_pager(
        profile,
        tmp_path,
        workspace_bundle_ref="workspace.json",
        manifest_ref="artifact:manifest.json",
    )

    expected = json.loads(json.dumps(build_one_pager(profile).as_dict()))
    assert json.loads(one_pager_path.read_text(encoding="utf-8")) == expected


def test_report_spec_compatibility_export_forwards_to_canonical_path(tmp_path: Path) -> None:
    compatibility_dir = tmp_path / "compatibility"
    canonical_dir = tmp_path / "canonical"

    compatibility_paths = compatibility_export_one_pager(
        _profile(),
        compatibility_dir,
        workspace_bundle_ref="workspace.json",
        manifest_ref="artifact:manifest.json",
    )
    canonical_paths = export_one_pager(
        _profile(),
        canonical_dir,
        workspace_bundle_ref="workspace.json",
        manifest_ref="artifact:manifest.json",
    )

    assert [path.read_bytes() for path in compatibility_paths] == [
        path.read_bytes() for path in canonical_paths
    ]


@pytest.mark.parametrize(
    "workspace_path",
    [
        "",
        " /workspace.json",
        "/workspace.json",
        "../workspace.json",
        "a/../workspace.json",
        "C:/workspace.json",
        "//server/share.json",
        "a\\workspace.json",
        "workspace/",
    ],
)
def test_report_spec_rejects_unsafe_workspace_paths(tmp_path: Path, workspace_path: str) -> None:
    output_dir = tmp_path / "export"
    with pytest.raises(ValueError, match="run-relative POSIX file path"):
        export_one_pager(
            _profile(),
            output_dir,
            workspace_bundle_ref=workspace_path,
            manifest_ref="artifact:manifest.json",
        )

    assert not output_dir.exists()
