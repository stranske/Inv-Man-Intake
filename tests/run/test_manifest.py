"""Acceptance test for the per-run ``manifest.json`` (#474)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inv_man_intake.intake.versioning import compute_sha256
from inv_man_intake.run import ARTIFACT_MANIFEST, run_pipeline
from inv_man_intake.run_manifest import build_manifest

_BUNDLE = Path("tests/fixtures/intake/pdf_primary_mixed_bundle.json")


def test_manifest_hashes_every_non_manifest_artifact(tmp_path: Path) -> None:
    run_pipeline(_BUNDLE, output_dir=tmp_path)

    manifest_path = tmp_path / ARTIFACT_MANIFEST
    assert manifest_path.is_file(), "run did not write manifest.json"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {entry["name"]: entry for entry in manifest["artifacts"]}

    on_disk = {p.name for p in tmp_path.iterdir() if p.name != ARTIFACT_MANIFEST}
    assert set(entries) == on_disk, "manifest must list exactly the non-manifest files"

    for name, entry in entries.items():
        content = (tmp_path / name).read_bytes()
        assert entry["sha256"] == compute_sha256(content)
        assert entry["bytes"] == len(content)
        assert entry["path"] == name
        assert entry["artifact_id"]
        assert entry["kind"]

    # The manifest itself is not one of its own entries, and it records the run.
    assert ARTIFACT_MANIFEST not in entries
    assert manifest["run_id"]
    assert "trace_id" in manifest


def test_run_json_carries_manifest_pointer(tmp_path: Path) -> None:

    run_pipeline(_BUNDLE, output_dir=tmp_path)
    run_payload = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))

    assert run_payload["manifest"] == f"artifact:{ARTIFACT_MANIFEST}"


def test_build_manifest_rejects_unsafe_artifact_refs(tmp_path: Path) -> None:
    # A ``..`` traversal segment in the path is rejected before any read.
    with pytest.raises(ValueError):
        build_manifest("run-1", None, [tmp_path / "sub" / ".." / "escape.json"])

    # A name that is itself a ``..`` segment yields an unsafe ``artifact:`` ref.
    with pytest.raises(ValueError):
        build_manifest("run-1", None, [tmp_path / "child" / ".."])
