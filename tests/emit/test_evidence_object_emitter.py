"""Acceptance coverage for the evidence-object/v1 run emitter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from tests.conftest import stage_headless_reference_bundle

from inv_man_intake.emit.evidence_objects import build_evidence_objects
from inv_man_intake.emit.validate_evidence import Report, _load_emitted_evidence, validate_envelope
from inv_man_intake.emit.validate_evidence import main as validate_run_contract
from inv_man_intake.extraction.providers.pptx_primary import PptxPrimaryExtractionProvider
from inv_man_intake.run import _source_location_payload, run_pipeline

_EVIDENCE_SCHEMA_PATH = Path("docs/contracts/schemas/evidence-object-v1.schema.json")


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


def _evidence_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_EVIDENCE_SCHEMA_PATH.read_text(encoding="utf-8")))


def _paged_field(source_page: int, *, key: str = "terms.management_fee") -> dict[str, Any]:
    return {
        "key": key,
        "source_doc_id": "doc_paged",
        "source_page": source_page,
        "method": "pptx-primary",
        "snippet": "Management fee: 1.25%",
        "confidence": 0.93,
        "location": {
            "source_doc_id": "doc_paged",
            "source_page": source_page,
            "table_index": 2,
            "bbox": [1, 2, 3, 4],
        },
    }


def test_one_based_provider_pages_emit_zero_based_locator() -> None:
    validator = _evidence_validator()
    expected_pages = {1: 0, 3: 2}
    for provider_page, locator_page in expected_pages.items():
        (evidence,) = build_evidence_objects([_paged_field(provider_page)])
        validator.validate(evidence)
        assert evidence["locator"] == {
            "page": locator_page,
            "table_index": 2,
            "bbox": [1.0, 2.0, 3.0, 4.0],
        }

    (unknown,) = build_evidence_objects([_paged_field(0)])
    validator.validate(unknown)
    assert "page" not in unknown["locator"]
    assert unknown["locator"] == {"table_index": 2, "bbox": [1.0, 2.0, 3.0, 4.0]}

    location_only = _paged_field(3)
    location_only.pop("source_page")
    (from_location,) = build_evidence_objects([location_only])
    assert from_location["locator"]["page"] == 2

    unknown_only = _paged_field(0)
    unknown_only["location"] = {"source_doc_id": "doc_paged", "source_page": 0}
    (no_locator,) = build_evidence_objects([unknown_only])
    validator.validate(no_locator)
    assert "locator" not in no_locator


def test_negative_provider_page_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_page must be non-negative"):
        build_evidence_objects([_paged_field(-1)])


def test_pptx_provider_slides_emit_zero_based_locators_deterministically() -> None:
    result = PptxPrimaryExtractionProvider().extract(
        source_doc_id="doc_pptx_1",
        content=Path("tests/fixtures/extraction/harborline_strategy_review.pptx").read_bytes(),
    )
    fields = [
        {
            "key": field.key,
            "value": field.value,
            "confidence": field.confidence,
            "source_doc_id": field.source_doc_id,
            "source_page": field.source_page,
            "method": field.method,
            "location": _source_location_payload(field.location),
            "snippet": field.snippet,
        }
        for field in result.fields
    ]
    slides = {field.key: field.source_page for field in result.fields}
    assert slides["strategy.asset_class"] == 1
    assert slides["operations.aum"] == 2

    first = build_evidence_objects(fields)
    second = build_evidence_objects([dict(field) for field in fields])

    validator = _evidence_validator()
    for evidence in first:
        validator.validate(evidence)
    pages = {evidence["fact_ref"]: evidence["locator"]["page"] for evidence in first}
    assert pages == {key: slide - 1 for key, slide in slides.items()}
    assert pages["strategy.asset_class"] == 0
    assert pages["operations.aum"] == 1
    assert [item["evidence_id"] for item in first] == [item["evidence_id"] for item in second]
    assert first == second


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


@pytest.mark.parametrize("artifacts", [None, {}, [None], ["evidence.json"]])
def test_run_contract_validator_rejects_malformed_manifest_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], artifacts: object
) -> None:
    run_path = tmp_path / "run.json"
    manifest_path = tmp_path / "manifest.json"
    registry_path = tmp_path / "registry.json"
    run_path.write_text(json.dumps(_valid_envelope()), encoding="utf-8")
    manifest_path.write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")
    _write_registry(registry_path)

    assert (
        validate_run_contract(
            [
                str(run_path),
                "--manifest",
                str(manifest_path),
                "--registry",
                str(registry_path),
                "--schema-dir",
                "docs/contracts/schemas",
                "--repo",
                "stranske/Inv-Man-Intake",
            ]
        )
        == 2
    )
    assert "manifest artifact" in capsys.readouterr().err


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
