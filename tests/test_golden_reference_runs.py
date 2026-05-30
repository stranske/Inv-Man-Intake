"""Golden reference-run gate for the extraction-threshold decision branches.

Each scenario bundle under ``tests/fixtures/intake/reference_*_bundle.json`` is
run through the real ``evaluate_thresholds`` decision core and its deterministic
golden subset is compared byte-for-byte against the committed golden in
``tests/fixtures/golden/``. This catches silent regressions in the auto-pass /
missing-mandatory / confidence-below-threshold branches that the single
escalate-shaped acceptance smoke fixture does not cover.

Regenerate the committed goldens after an intentional decision-contract change::

    python -m inv_man_intake.reference_runs --regenerate
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inv_man_intake.reference_runs import (
    GOLDEN_ROOT,
    REFERENCE_SCENARIOS,
    build_reference_run,
    iter_reference_runs,
    load_bundle,
    main,
    regenerate_goldens,
    serialize_reference_run,
)

_FIXTURE_ROOT = Path("tests/fixtures/intake")


@pytest.mark.parametrize(("bundle_name", "golden_name"), REFERENCE_SCENARIOS)
def test_reference_run_matches_committed_golden(bundle_name: str, golden_name: str) -> None:
    bundle = load_bundle(_FIXTURE_ROOT / bundle_name)
    produced = serialize_reference_run(build_reference_run(bundle))
    committed = (GOLDEN_ROOT / golden_name).read_text(encoding="utf-8")
    assert produced == committed, (
        f"{golden_name} diverged from the committed golden; "
        "regenerate intentionally with `python -m inv_man_intake.reference_runs --regenerate`"
    )


def test_reference_run_gate_fails_when_a_golden_is_mutated(tmp_path: Path) -> None:
    """The gate must fail when any deterministic field drifts from the golden."""

    bundle_name, golden_name = REFERENCE_SCENARIOS[0]
    produced = build_reference_run(load_bundle(_FIXTURE_ROOT / bundle_name))

    mutated = json.loads((GOLDEN_ROOT / golden_name).read_text(encoding="utf-8"))
    mutated["decision"]["auto_pass_document"] = not mutated["decision"]["auto_pass_document"]
    mutated_path = tmp_path / golden_name
    mutated_path.write_text(serialize_reference_run(mutated), encoding="utf-8")

    assert serialize_reference_run(produced) != mutated_path.read_text(encoding="utf-8")


def test_auto_pass_scenario_takes_the_auto_pass_branch() -> None:
    payload = build_reference_run(load_bundle(_FIXTURE_ROOT / "reference_auto_pass_bundle.json"))
    assert payload["decision"]["auto_pass_document"] is True
    assert payload["decision"]["escalate"] is False
    assert payload["decision"]["escalation_reason"] == "none"


def test_missing_mandatory_scenario_takes_the_missing_field_branch() -> None:
    payload = build_reference_run(
        load_bundle(_FIXTURE_ROOT / "reference_missing_mandatory_bundle.json")
    )
    assert payload["decision"]["auto_pass_document"] is False
    assert payload["decision"]["escalate"] is True
    assert payload["decision"]["escalation_reason"] == "missing_mandatory_field:operations.aum"


def test_below_threshold_scenario_takes_the_confidence_branch() -> None:
    payload = build_reference_run(
        load_bundle(_FIXTURE_ROOT / "reference_confidence_below_threshold_bundle.json")
    )
    assert payload["decision"]["auto_pass_document"] is False
    assert payload["decision"]["escalate"] is True
    assert payload["decision"]["escalation_reason"] == "confidence_below_threshold:operations.aum"


def test_regenerate_is_idempotent_against_committed_goldens(tmp_path: Path) -> None:
    """`--regenerate` into a temp dir must reproduce the committed goldens exactly."""

    written = regenerate_goldens(fixture_root=_FIXTURE_ROOT, golden_root=tmp_path)
    assert {path.name for path in written} == {golden for _, golden in REFERENCE_SCENARIOS}
    for path in written:
        assert path.read_text(encoding="utf-8") == (GOLDEN_ROOT / path.name).read_text(
            encoding="utf-8"
        )


def test_cli_default_prints_every_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--fixture-root", str(_FIXTURE_ROOT)])
    assert exit_code == 0
    out = capsys.readouterr().out
    for _, golden_name in REFERENCE_SCENARIOS:
        assert golden_name in out
    # Sanity: the printed payloads cover all three decision branches.
    assert "missing_mandatory_field:operations.aum" in out
    assert "confidence_below_threshold:operations.aum" in out


def test_iter_reference_runs_covers_all_scenarios() -> None:
    runs = iter_reference_runs(fixture_root=_FIXTURE_ROOT)
    assert {golden for golden, _ in runs} == {golden for _, golden in REFERENCE_SCENARIOS}
