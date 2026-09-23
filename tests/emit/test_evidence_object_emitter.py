"""Acceptance coverage for the evidence-object/v1 run emitter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from tests.conftest import stage_headless_reference_bundle

from inv_man_intake.emit.validate_evidence import Report, _load_emitted_evidence, validate_envelope
from inv_man_intake.emit.validate_evidence import main as validate_run_contract
from inv_man_intake.run import run_pipeline


def _write_registry(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "participants": [
                    {
                        "repo": "stranske/Inv-Man-Intake",
                        "role": "producer",
                        "status": "conformant",
                        "required_sections": ["evidence_refs", "identity_refs", "latency"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _registry() -> dict[str, Any]:
    return {
        "participants": [
            {
                "repo": "stranske/Inv-Man-Intake",
                "role": "producer",
                "status": "conformant",
                "required_sections": ["evidence_refs", "identity_refs", "latency"],
            }
        ]
    }


def _valid_envelope(*evidence_refs: object) -> dict[str, Any]:
    return {
        "schema_version": "run-contract/v1",
        "repo": "stranske/Inv-Man-Intake",
        "tool": "test-emitter",
        "run_id": "run:test",
        "status": "success",
        "github_issue": "stranske/Inv-Man-Intake#949",
        "actor": {"kind": "agent", "id": "test"},
        "inputs": {"validated": True},
        "outputs": {"manifest_ref": "manifest.json"},
        "provenance": {"tool_version": "test"},
        "latency": {"wall_ms": 1},
        "identity_refs": [],
        "evidence_refs": list(evidence_refs),
    }


def _evidence(evidence_id: str = "evidence:sha256:test") -> dict[str, Any]:
    return {
        "schema_version": "evidence-object/v1",
        "evidence_id": evidence_id,
        "fact_ref": "field:test",
        "source_id": "document:test",
        "method": "parser",
        "excerpt": "Test excerpt",
    }


def _validate(envelope: dict[str, Any], evidence_objects: list[dict[str, Any]] | None) -> Report:
    return validate_envelope(
        envelope=envelope,
        schema_dir=Path("docs/contracts/schemas"),
        registry=_registry(),
        repo="stranske/Inv-Man-Intake",
        manifest=None,
        evidence_objects=evidence_objects,
    )


def test_run_evidence_refs_are_evidence_ids(tmp_path: Path) -> None:
    bundle_path = stage_headless_reference_bundle(tmp_path)
    output_dir = tmp_path / "out"
    run_pipeline(bundle_path, output_dir=output_dir)

    run_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    evidence_paths = sorted(output_dir.glob("evidence-*.json"))
    evidence_objects = [json.loads(path.read_text(encoding="utf-8")) for path in evidence_paths]
    evidence_ids = sorted(item["evidence_id"] for item in evidence_objects)

    assert evidence_paths
    assert len(evidence_paths) == len(run_payload["fields"])
    assert run_payload["evidence_refs"] == evidence_ids
    assert all(ref.startswith("evidence:sha256:") for ref in evidence_ids)
    assert all("#page=" not in ref for ref in evidence_ids)

    schema = json.loads(
        Path("docs/contracts/schemas/evidence-object-v1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    for evidence in evidence_objects:
        validator.validate(evidence)

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_evidence = {
        item["name"] for item in manifest["artifacts"] if item.get("kind") == "evidence"
    }
    assert {path.name for path in evidence_paths} <= manifest_evidence


def test_run_contract_validator_rejects_malformed_emitted_evidence(tmp_path: Path) -> None:
    bundle_path = stage_headless_reference_bundle(tmp_path)
    output_dir = tmp_path / "out"
    run_pipeline(bundle_path, output_dir=output_dir)
    registry = tmp_path / "registry.json"
    _write_registry(registry)
    args = [
        str(output_dir / "run.json"),
        "--manifest",
        str(output_dir / "manifest.json"),
        "--registry",
        str(registry),
        "--schema-dir",
        "docs/contracts/schemas",
        "--repo",
        "stranske/Inv-Man-Intake",
    ]
    assert validate_run_contract(args) == 0

    evidence_path = next(output_dir.glob("evidence-*.json"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence.pop("excerpt")
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    assert validate_run_contract(args) == 1


@pytest.mark.parametrize("document", ["run", "manifest", "registry"])
def test_run_contract_validator_rejects_non_object_cli_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], document: str
) -> None:
    paths = {name: tmp_path / f"{name}.json" for name in ("run", "manifest", "registry")}
    for path in paths.values():
        path.write_text("[]", encoding="utf-8")
    args = [
        str(paths["run"]),
        "--manifest",
        str(paths["manifest"]),
        "--registry",
        str(paths["registry"]),
        "--schema-dir",
        "docs/contracts/schemas",
        "--repo",
        "stranske/Inv-Man-Intake",
    ]
    for name, path in paths.items():
        if name != document:
            path.write_text("{}", encoding="utf-8")

    assert validate_run_contract(args) == 2
    assert "must be an object" in capsys.readouterr().err


def test_validate_envelope_reports_dangling_evidence_ref() -> None:
    report = _validate(_valid_envelope("evidence:sha256:missing"), [])

    assert any(
        "has no emitted evidence-object/v1 file" in item.message for item in report.violations
    )


def test_validate_envelope_reports_orphan_evidence_object() -> None:
    report = _validate(_valid_envelope(), [_evidence()])

    assert any(
        "is not referenced by the run envelope" in item.message for item in report.violations
    )


def test_validate_envelope_reports_duplicate_evidence_id() -> None:
    evidence_id = "evidence:sha256:duplicate"
    report = _validate(
        _valid_envelope(evidence_id), [_evidence(evidence_id), _evidence(evidence_id)]
    )

    assert any("duplicate emitted evidence_id" in item.message for item in report.violations)


def test_validate_envelope_without_manifest_skips_evidence_resolution() -> None:
    assert _load_emitted_evidence(run_dir=Path("."), manifest=None) is None

    report = _validate(_valid_envelope("evidence:sha256:not-loaded"), None)

    assert report.conformant


def test_validate_envelope_reports_non_string_ref_without_crashing() -> None:
    report = _validate(_valid_envelope(["not", "hashable"]), [])

    assert not report.conformant
    assert any(item.path == "evidence_refs/0" for item in report.violations)
