"""Acceptance test for the headless ``inv-man-ingest`` entry point (#473)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from inv_man_intake.cli.ingest import main

_BUNDLE = "tests/fixtures/intake/pdf_primary_mixed_bundle.json"
_FIXTURE_EXTRACTION = Path("tests/fixtures/extraction")
_ARTIFACT_FILES = (
    "run.json",
    "metadata.json",
    "threshold-summary.json",
    "explainability.json",
)
_KEY_FIELDS = (
    "strategy.asset_class",
    "terms.management_fee",
    "performance.net_return_1y",
    "operations.aum",
    "team.key_person_risk",
)


def _minimal_external_bundle_payload() -> dict[str, object]:
    base = json.loads(Path(_BUNDLE).read_text(encoding="utf-8"))
    files = [
        entry
        for entry in base["files"]
        if entry["file_name"]
        in {
            "summit_arc_investment_update.pdf",
            "summit_arc_track_record.xlsx",
        }
    ]
    payload = dict(base)
    payload["files"] = files
    return payload


def _write_external_layout_bundle(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    bundle_payload = _minimal_external_bundle_payload()
    for entry in bundle_payload["files"]:
        source = _FIXTURE_EXTRACTION / entry["file_name"]
        target = tmp_path / entry["file_name"]
        shutil.copyfile(source, target)
    bundle_path = tmp_path / "external_intake_bundle.json"
    bundle_path.write_text(json.dumps(bundle_payload, indent=2) + "\n", encoding="utf-8")
    return bundle_path


def test_ingest_entrypoint_writes_run_and_named_artifacts(tmp_path: Path) -> None:
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    output_dir = tmp_path / "out"
    exit_code = main([str(bundle_path), "--out", str(output_dir)])

    assert exit_code == 0
    for name in _ARTIFACT_FILES:
        assert (output_dir / name).is_file(), f"missing artifact on disk: {name}"


def test_ingest_run_json_carries_score_escalation_and_evidence(tmp_path: Path) -> None:
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    output_dir = tmp_path / "out"
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0

    run_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))

    assert run_payload["final_score"] == pytest.approx(0.7809)
    assert run_payload["escalation_state"]["reason"] == "low_key_field_coverage"

    evidence = run_payload["provenance"]["evidence"]
    fields_by_key = {field["key"]: field for field in run_payload["fields"]}
    for key in _KEY_FIELDS:
        assert key in evidence, f"missing evidence pointer for key field {key}"
        pointer = evidence[key]
        assert pointer["source_doc_id"]
        assert pointer["source_page"] is not None
        assert isinstance(pointer["confidence"], (int, float))
        assert isinstance(pointer["method"], str)
        assert pointer["method"]
        assert "value" not in pointer
        assert isinstance(pointer["snippet"], str)
        assert pointer["snippet"]

        location = pointer["location"]
        assert isinstance(location, dict)
        assert location["source_doc_id"] == pointer["source_doc_id"]
        assert location["source_page"] == pointer["source_page"]

        metadata = pointer["snippet_metadata"]
        assert isinstance(metadata, dict)
        assert metadata["kind"] == "regex-match"
        assert isinstance(metadata["char_start"], int)
        assert isinstance(metadata["char_end"], int)
        assert metadata["char_end"] >= metadata["char_start"]

        field_entry = fields_by_key[key]
        assert isinstance(field_entry["method"], str)
        assert field_entry["method"]
        assert field_entry["confidence"] == pointer["confidence"]
        assert field_entry["location"] == location
        assert field_entry["snippet"] == pointer["snippet"]
        assert field_entry["snippet_metadata"] == metadata


def test_ingest_entrypoint_returns_nonzero_for_missing_bundle(tmp_path: Path) -> None:
    exit_code = main([str(tmp_path / "missing.json"), "--out", str(tmp_path / "out")])

    assert exit_code != 0


def test_ingest_entrypoint_returns_nonzero_for_rejected_bundle(tmp_path: Path) -> None:
    exit_code = main(
        ["tests/fixtures/intake/malformed_missing_metadata.json", "--out", str(tmp_path)]
    )

    assert exit_code == 1


def test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout(
    tmp_path: Path,
) -> None:
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    output_dir = tmp_path / "output"

    exit_code = main([str(bundle_path), "--out", str(output_dir)])

    assert exit_code == 0
    for name in _ARTIFACT_FILES:
        assert (output_dir / name).is_file(), f"missing artifact on disk: {name}"


def test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout_break(
    tmp_path: Path,
) -> None:
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    output_dir = tmp_path / "output"
    track_record = bundle_path.parent / "summit_arc_track_record.xlsx"
    submitted_bytes = track_record.read_bytes()

    # Corrupt the submitted file, leaving the real resolver and repository fixture intact.
    # A resolver that silently falls back to that fixture would incorrectly succeed.
    track_record.write_bytes(b"not-the-submitted-workbook")
    assert main([str(bundle_path), "--out", str(output_dir)]) != 0

    track_record.write_bytes(submitted_bytes)
    restored_output = output_dir / "restored"
    assert main([str(bundle_path), "--out", str(restored_output)]) == 0
    for name in _ARTIFACT_FILES:
        assert (restored_output / name).is_file(), f"missing artifact on disk: {name}"


def test_ingest_entrypoint_rejects_bundle_file_name_escape(tmp_path: Path) -> None:
    bundle_path = tmp_path / "escape_bundle.json"
    bundle_path.write_text(
        json.dumps(
            {
                "package_id": "pkg_escape_001",
                "metadata": {
                    "firm_name": "Summit Arc Advisors",
                    "fund_name": "Summit Arc Special Situations",
                    "received_at": "2026-03-04T08:20:00Z",
                    "source_channel": "internal_forward",
                },
                "files": [
                    {
                        "file_name": "../extraction/summit_arc_investment_update.pdf",
                        "role": "investment_deck",
                        "source_ref": "email:fwd-7421",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main([str(bundle_path), "--out", str(tmp_path / "out")])

    assert exit_code != 0


def test_fixture_bytes_rejects_escape_before_read(tmp_path: Path) -> None:
    from inv_man_intake.v1_smoke import _fixture_bytes

    fixture_root = tmp_path / "intake"
    fixture_root.mkdir()
    (tmp_path / "extraction").mkdir()
    (tmp_path / "outside.pdf").write_bytes(b"outside-content")
    with pytest.raises(ValueError, match="escapes the content base directory"):
        _fixture_bytes(fixture_root=fixture_root, file_name="../outside.pdf")
