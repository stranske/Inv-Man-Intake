"""Acceptance test for the headless ``inv-man-ingest`` entry point (#473)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inv_man_intake.cli.ingest import main

_BUNDLE = "tests/fixtures/intake/pdf_primary_mixed_bundle.json"
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


def test_ingest_entrypoint_writes_run_and_named_artifacts(tmp_path: Path) -> None:
    exit_code = main([_BUNDLE, "--out", str(tmp_path)])

    assert exit_code == 0
    for name in _ARTIFACT_FILES:
        assert (tmp_path / name).is_file(), f"missing artifact on disk: {name}"


def test_ingest_run_json_carries_score_escalation_and_evidence(tmp_path: Path) -> None:
    assert main([_BUNDLE, "--out", str(tmp_path)]) == 0

    run_payload = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))

    assert run_payload["final_score"] == pytest.approx(0.7809)
    assert run_payload["escalation_state"]["reason"] == "low_key_field_coverage"

    evidence = run_payload["provenance"]["evidence"]
    for key in _KEY_FIELDS:
        assert key in evidence, f"missing evidence pointer for key field {key}"
        pointer = evidence[key]
        assert pointer["source_doc_id"]
        assert pointer["source_page"] is not None


def test_ingest_entrypoint_returns_nonzero_for_missing_bundle(tmp_path: Path) -> None:
    exit_code = main([str(tmp_path / "missing.json"), "--out", str(tmp_path / "out")])

    assert exit_code != 0


def test_ingest_entrypoint_returns_nonzero_for_rejected_bundle(tmp_path: Path) -> None:
    exit_code = main(
        ["tests/fixtures/intake/malformed_missing_metadata.json", "--out", str(tmp_path)]
    )

    assert exit_code == 1
