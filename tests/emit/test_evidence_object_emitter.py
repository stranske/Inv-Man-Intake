"""Acceptance coverage for the evidence-object/v1 run emitter."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from scripts.validate_run_contract import main as validate_run_contract
from tests.conftest import stage_headless_reference_bundle

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
