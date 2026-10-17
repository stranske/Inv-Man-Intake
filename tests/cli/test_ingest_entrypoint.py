"""Acceptance test for the headless ``inv-man-ingest`` entry point (#473)."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
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


@pytest.mark.parametrize("toggle", ["false", "true", None])
def test_ingest_ignores_langsmith_key_when_tracing_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toggle: str | None
) -> None:
    """Production stays offline even with credentials and ambient opt-in toggles."""
    from inv_man_intake.observability import langsmith_sink

    monkeypatch.setenv("LANGSMITH_API_KEY", "fake-offline-regression-key")
    for key in ("INV_MAN_TRACING_ENABLED", "LANGSMITH_TRACING_ENABLED", "LANGCHAIN_TRACING_V2"):
        if toggle is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, toggle)
    calls = []

    def forbidden_client():
        calls.append("client")
        raise AssertionError("production ingest must never construct a remote trace client")

    monkeypatch.setattr(langsmith_sink, "_default_client_factory", forbidden_client)
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    output_dir = tmp_path / "out"
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0
    assert json.loads((output_dir / "run.json").read_text())["run_id"]
    assert calls == []


def test_ingest_run_json_carries_score_escalation_and_evidence(tmp_path: Path) -> None:
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    output_dir = tmp_path / "out"
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0

    run_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))

    assert run_payload["final_score"] is None
    assert run_payload["explainability"]["status"] == "unavailable"
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


@pytest.mark.parametrize(
    "primary", ["summit_arc_investment_update.pdf", "harborline_strategy_review.pptx"]
)
def test_ingest_primary_only_pdf_and_pptx(tmp_path, monkeypatch, primary):
    from inv_man_intake import v1_smoke

    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle.read_text())
    entry = payload["files"][0]
    entry["file_name"] = primary
    shutil.copyfile(_FIXTURE_EXTRACTION / primary, bundle.parent / primary)
    payload["files"] = [entry]
    bundle.write_text(json.dumps(payload))

    def no_fixture_performance():
        pytest.fail("primary-only production ingest must not invent fixture returns")

    monkeypatch.setattr(v1_smoke, "_fixture_performance_series", no_fixture_performance)
    output = tmp_path / "out"
    assert main([str(bundle), "--out", str(output)]) == 0
    result = json.loads((output / "run.json").read_text())
    assert result["performance"]["monthly"] is None
    assert result["performance"]["status"] == "unavailable"
    assert "performance:unavailable" in {warning["code"] for warning in result["warnings"]}
    assert result["final_score"] is None


@pytest.mark.parametrize("extension", ["docx", "eml", "txt", "md"])
@pytest.mark.parametrize("reverse", [False, True])
def test_ingest_primary_with_non_workbook_secondary(tmp_path, monkeypatch, extension, reverse):
    """Supported attachments must not enter the XLSX-only secondary boundary."""
    from inv_man_intake import v1_smoke

    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle.read_text())
    attachment_name = f"supporting_material.{extension}"
    payload["files"][1] = {
        "file_name": attachment_name,
        "role": "supporting_material",
        "source_ref": "email:test-optional-attachment",
    }
    (bundle.parent / attachment_name).write_bytes(b"supported attachment; not a workbook")
    if reverse:
        payload["files"].reverse()
    bundle.write_text(json.dumps(payload))

    def forbidden_secondary(**kwargs):
        pytest.fail("a non-workbook attachment entered the workbook boundary")

    monkeypatch.setattr(v1_smoke, "_run_secondary_extraction_boundary_smoke", forbidden_secondary)
    output = tmp_path / "out"
    assert main([str(bundle), "--out", str(output)]) == 0
    result = json.loads((output / "run.json").read_text())
    assert result["performance"]["monthly"] is None
    assert result["performance"]["status"] == "unavailable"
    assert result["fields"]
    primary_index = 1 if reverse else 0
    expected_id = f"{payload['package_id']}:doc:{primary_index}"
    assert {pointer["source_doc_id"] for pointer in result["provenance"]["evidence"].values()} == {
        expected_id
    }


def test_ingest_file_order_permutations_equivalent(tmp_path):
    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle.read_text())
    workbook = bundle.parent / "summit_arc_track_record.xlsx"
    _write_performance_workbook(workbook, [("2024-01-31", 0.12), ("2024-02-29", -0.07)])
    results = []
    for index, files in enumerate([payload["files"], list(reversed(payload["files"]))]):
        bundle.write_text(json.dumps({**payload, "files": files}))
        output = tmp_path / f"out-{index}"
        assert main([str(bundle), "--out", str(output)]) == 0
        result = json.loads((output / "run.json").read_text())
        results.append(result)
        primary_index = next(
            i for i, entry in enumerate(files) if entry["file_name"].endswith(".pdf")
        )
        expected_id = f"{payload['package_id']}:doc:{primary_index}"
        assert result["fields"]
        for pointer in result["provenance"]["evidence"].values():
            assert pointer["source_doc_id"] == expected_id
    values = [{row["key"]: row["value"] for row in result["fields"]} for result in results]
    assert values[0] == values[1]
    assert results[0]["performance"]["monthly"] == results[1]["performance"]["monthly"]
    assert results[0]["performance"]["monthly"] == [
        {"as_of": "2024-01-31", "value": 0.12},
        {"as_of": "2024-02-29", "value": -0.07},
    ]


def test_ingest_malformed_primary_is_controlled_failure(tmp_path):
    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    (bundle.parent / "summit_arc_investment_update.pdf").write_bytes(b"not a PDF")
    assert main([str(bundle), "--out", str(tmp_path / "out")]) == 1


def test_ingest_entrypoint_returns_nonzero_for_rejected_bundle(tmp_path: Path) -> None:
    exit_code = main(
        ["tests/fixtures/intake/malformed_missing_metadata.json", "--out", str(tmp_path)]
    )

    assert exit_code == 1


def _write_performance_workbook(path: Path, rows: list[tuple[object, ...]]) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("as_of", "value"))
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


@pytest.mark.parametrize(
    "workbook_dates",
    [
        (datetime(2024, 1, 31), date(2024, 2, 29), "2024-03-31"),
        (datetime(2024, 1, 15), date(2024, 2, 10), "2024-03-20"),
    ],
    ids=["period-end", "mid-month"],
)
def test_ingest_entrypoint_runs_valid_bundle_outside_repository_fixture_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    workbook_dates: tuple[datetime, date, str],
) -> None:
    from inv_man_intake import v1_smoke

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    bundle = json.loads(bundle_path.read_text())
    renamed_workbook = "submitted-manager-returns.xlsx"
    for entry in bundle["files"]:
        if entry["role"] == "performance_track_record":
            (bundle_path.parent / entry["file_name"]).unlink()
            entry["file_name"] = renamed_workbook
    bundle_path.write_text(json.dumps(bundle))
    rows = list(zip(workbook_dates, (0.12, -0.07, 0.03), strict=True))
    _write_performance_workbook(bundle_path.parent / renamed_workbook, rows)

    def forbidden_fixture(*args, **kwargs):
        pytest.fail("production must not read fixture bytes or performance")

    monkeypatch.setattr(v1_smoke, "_fixture_bytes", forbidden_fixture)
    monkeypatch.setattr(v1_smoke, "_fixture_performance_series", forbidden_fixture)
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "output"
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0
    for name in _ARTIFACT_FILES:
        assert (output_dir / name).is_file()
    run = json.loads((output_dir / "run.json").read_text())
    performance = run["performance"]
    assert performance["monthly"] == [
        {"as_of": "2024-01-31", "value": 0.12},
        {"as_of": "2024-02-29", "value": -0.07},
        {"as_of": "2024-03-31", "value": 0.03},
    ]
    assert performance["status"] == "available"
    assert performance["source"] == "submitted_workbook"
    assert performance["comparison_available"] is False
    assert performance["benchmark_available"] is False
    assert performance["metrics"]["benchmark_correlation"] is None
    assert isinstance(run["final_score"], float)

    # A changed submission must change the artifact, not reuse any fixed series.
    rows[0] = ("2024-01-31", 0.24)
    _write_performance_workbook(bundle_path.parent / renamed_workbook, rows)
    assert main([str(bundle_path), "--out", str(tmp_path / "changed")]) == 0
    changed = json.loads((tmp_path / "changed" / "run.json").read_text())
    assert changed["performance"]["monthly"][0]["value"] == 0.24
    assert changed["performance"]["metrics"] != performance["metrics"]
    assert changed["final_score"] != run["final_score"]


_SCORE_ROWS = [("2024-01-31", 0.12), ("2024-02-29", -0.07), ("2024-03-31", 0.03)]


def _write_score_bundle(
    tmp_path: Path,
    *,
    name: str,
    rows: list | None = None,
    pdf_replacements: tuple[tuple[bytes, bytes], ...] = (),
) -> Path:
    bundle_path = _write_external_layout_bundle(tmp_path / name)
    _write_performance_workbook(
        bundle_path.parent / "summit_arc_track_record.xlsx",
        _SCORE_ROWS if rows is None else rows,
    )
    if pdf_replacements:
        pdf_path = bundle_path.parent / "summit_arc_investment_update.pdf"
        data = pdf_path.read_bytes()
        for old, new in pdf_replacements:
            assert old in data
            data = data.replace(old, new)
        pdf_path.write_bytes(data)
    return bundle_path


def _run_score(bundle_path: Path, output_dir: Path) -> dict:
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0
    return json.loads((output_dir / "run.json").read_text(encoding="utf-8"))


def _component_scores(run: dict) -> dict[str, float]:
    return {
        item["component"]: item["contribution"] / item["weight"]
        for item in run["explainability"]["components"]
        if item["weight"]
    }


def test_ingest_score_numeric_for_two_supported_asset_classes(tmp_path: Path) -> None:
    runs = {}
    for label, asset_text in (("credit", b"credit"), ("quant", b"quant")):
        bundle = _write_score_bundle(
            tmp_path,
            name=f"bundle-{label}",
            pdf_replacements=((b"credit", asset_text),),
        )
        runs[label] = _run_score(bundle, tmp_path / f"out-{label}")

    for run in runs.values():
        assert isinstance(run["final_score"], float)
        explainability = run["explainability"]
        assert explainability["overall_score"] == pytest.approx(run["final_score"])
        assert explainability["total_contribution"] == pytest.approx(run["final_score"])
        assert explainability["total_contribution"] == pytest.approx(
            sum(item["contribution"] for item in explainability["components"])
        )
        assert not any(w["code"] == "scoring:unavailable" for w in run["warnings"])
        document_ids = run["inputs"]["document_ids"]
        for item in explainability["components"]:
            assert any(doc_id in item["rationale"] for doc_id in document_ids), item
            assert "page" in item["rationale"], item
    # Same evidence under different asset-class weights yields different totals.
    assert runs["credit"]["final_score"] != runs["quant"]["final_score"]
    credit_weights = {
        i["component"]: i["weight"] for i in runs["credit"]["explainability"]["components"]
    }
    quant_weights = {
        i["component"]: i["weight"] for i in runs["quant"]["explainability"]["components"]
    }
    assert credit_weights != quant_weights


def test_ingest_score_explainability_provenance_is_resolvable(tmp_path: Path) -> None:
    run = _run_score(_write_score_bundle(tmp_path, name="bundle-prov"), tmp_path / "out-prov")
    # Also verify the standalone artifact carries the same provenance.
    explainability_artifact = json.loads(
        (tmp_path / "out-prov" / "explainability.json").read_text(encoding="utf-8")
    )
    assert explainability_artifact == run["explainability"]

    document_ids = set(run["inputs"]["document_ids"])
    evidence = run["provenance"]["evidence"]
    components = {item["component"]: item for item in run["explainability"]["components"]}
    assert set(components) == {
        "performance_consistency",
        "risk_adjusted_returns",
        "operational_quality",
        "transparency",
        "team_experience",
    }
    for item in components.values():
        assert item["provenance"], item
        for provenance in item["provenance"]:
            assert provenance["source_doc_id"] in document_ids, provenance
            if provenance["source_kind"] == "document":
                field_evidence = evidence[provenance["reference"]]
                assert provenance["source_doc_id"] == field_evidence["source_doc_id"]
                assert provenance["source_page"] == field_evidence["source_page"]
                assert provenance["source_page"] is not None
            elif provenance["source_kind"] == "workbook":
                assert provenance["reference"].endswith(".xlsx"), provenance
            else:  # pragma: no cover - production components are doc/workbook only
                raise AssertionError(f"unexpected provenance {provenance}")
    # Component-specific pointers: workbook drives performance, AUM drives operations.
    assert any(
        p["source_kind"] == "workbook" for p in components["performance_consistency"]["provenance"]
    )
    assert any(
        p["reference"] == "operations.aum" for p in components["operational_quality"]["provenance"]
    )
    assert any(
        p["reference"] == "team.key_person_risk"
        for p in components["team_experience"]["provenance"]
    )


def test_ingest_score_within_class_aum_change_changes_operational_component(
    tmp_path: Path,
) -> None:
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-aum",
            pdf_replacements=((b"$1.2bn", b"$120m"),),
        ),
        tmp_path / "out-aum",
    )
    base_scores = _component_scores(baseline)
    changed_scores = _component_scores(changed)
    assert changed_scores["operational_quality"] != pytest.approx(
        base_scores["operational_quality"]
    )
    assert changed_scores["operational_quality"] < base_scores["operational_quality"]
    for component in (
        "performance_consistency",
        "risk_adjusted_returns",
        "transparency",
        "team_experience",
    ):
        assert changed_scores[component] == pytest.approx(base_scores[component]), component
    assert changed["final_score"] != pytest.approx(baseline["final_score"])


def test_ingest_score_fee_change_changes_only_operational_component(tmp_path: Path) -> None:
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-fee",
            pdf_replacements=((b"Management Fee: 1.25%", b"Management Fee: 2.50%"),),
        ),
        tmp_path / "out-fee",
    )
    base_scores = _component_scores(baseline)
    changed_scores = _component_scores(changed)
    # A higher management fee lowers operational quality and nothing else.
    assert changed_scores["operational_quality"] < base_scores["operational_quality"]
    for component in (
        "performance_consistency",
        "risk_adjusted_returns",
        "transparency",
        "team_experience",
    ):
        assert changed_scores[component] == pytest.approx(base_scores[component]), component
    assert changed["final_score"] < baseline["final_score"]


def test_ingest_score_net_return_change_changes_only_risk_adjusted_component(
    tmp_path: Path,
) -> None:
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-return",
            pdf_replacements=((b"Net Return 1Y: 8.4%", b"Net Return 1Y: 0.4%"),),
        ),
        tmp_path / "out-return",
    )
    base_scores = _component_scores(baseline)
    changed_scores = _component_scores(changed)
    # A lower extracted 1Y net return lowers risk-adjusted returns only.
    assert changed_scores["risk_adjusted_returns"] < base_scores["risk_adjusted_returns"]
    for component in (
        "performance_consistency",
        "operational_quality",
        "transparency",
        "team_experience",
    ):
        assert changed_scores[component] == pytest.approx(base_scores[component]), component
    assert changed["final_score"] < baseline["final_score"]


def test_ingest_score_key_person_change_changes_only_team_component(tmp_path: Path) -> None:
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-team",
            pdf_replacements=((b"one senior PM departure pending", b"low risk, stable team"),),
        ),
        tmp_path / "out-team",
    )
    base_scores = _component_scores(baseline)
    changed_scores = _component_scores(changed)
    # Baseline text carries a pending departure (0.35); low-risk text scores higher.
    assert base_scores["team_experience"] == pytest.approx(0.35)
    assert changed_scores["team_experience"] == pytest.approx(0.90)
    for component in (
        "performance_consistency",
        "risk_adjusted_returns",
        "operational_quality",
        "transparency",
    ):
        assert changed_scores[component] == pytest.approx(base_scores[component]), component
    assert changed["final_score"] > baseline["final_score"]


def test_ingest_score_natural_spellings_score_end_to_end(tmp_path: Path) -> None:
    """Spelled-out units and hyphenated risk text are submitted evidence too."""
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-spelled",
            pdf_replacements=(
                (b"credit", b"credit long/short"),
                (b"Management Fee: 1.25%", b"Management Fee: 125 bps"),
                (b"Net Return 1Y: 8.4%", b"Net Return 1Y: 8.4 percent"),
                (b"one senior PM departure pending", b"no key-person risk"),
            ),
        ),
        tmp_path / "out-spelled",
    )
    assert isinstance(changed["final_score"], float)
    base_scores = _component_scores(baseline)
    changed_scores = _component_scores(changed)
    # 125 bps == 1.25% and 8.4 percent == 8.4%: those components are unchanged.
    assert changed_scores["operational_quality"] == pytest.approx(
        base_scores["operational_quality"]
    )
    assert changed_scores["risk_adjusted_returns"] == pytest.approx(
        base_scores["risk_adjusted_returns"]
    )
    # The hyphenated no-risk text reads as reassuring, not the neutral default.
    assert changed_scores["team_experience"] == pytest.approx(0.90)
    assert changed["final_score"] != pytest.approx(baseline["final_score"])


def test_ingest_score_per_cent_and_departures_score_end_to_end(tmp_path: Path) -> None:
    """``per cent`` units and plural departures are submitted evidence too.

    Deliberate-break: reverting the ``per cent`` branch makes the fee
    unparseable (score unavailable); reverting the departure stems makes
    ``team_experience`` neutral (0.65) instead of adverse (0.35).
    """
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-per-cent",
            pdf_replacements=(
                (b"Management Fee: 1.25%", b"Management Fee: 1.25 per cent"),
                (b"Net Return 1Y: 8.4%", b"Net Return 1Y: 8.4 per cent"),
                (b"one senior PM departure pending", b"two senior departures announced"),
            ),
        ),
        tmp_path / "out-per-cent",
    )
    assert isinstance(changed["final_score"], float)
    base_scores = _component_scores(baseline)
    changed_scores = _component_scores(changed)
    assert changed_scores["operational_quality"] == pytest.approx(
        base_scores["operational_quality"]
    )
    assert changed_scores["risk_adjusted_returns"] == pytest.approx(
        base_scores["risk_adjusted_returns"]
    )
    assert changed_scores["team_experience"] == pytest.approx(0.35)


def test_ingest_score_singular_bp_mn_aum_and_left_score_end_to_end(tmp_path: Path) -> None:
    """Singular ``bp``, ``mn`` AUM, and ``has left`` text are submitted evidence.

    Deliberate-break: reverting the ``bp`` unit or ``mn`` multiplier makes
    scoring unavailable; reverting the ``left`` stem makes
    ``team_experience`` neutral (0.65) instead of adverse (0.35).
    """
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-bp-mn",
            pdf_replacements=(
                (b"Management Fee: 1.25%", b"Management Fee: 125 bp"),
                (b"$1.2bn", b"$1,200mn"),
                (b"one senior PM departure pending", b"key person has left"),
            ),
        ),
        tmp_path / "out-bp-mn",
    )
    assert isinstance(changed["final_score"], float)
    base_scores = _component_scores(baseline)
    changed_scores = _component_scores(changed)
    # 125 bp == 1.25% and $1,200mn == $1.2bn: operational quality is unchanged.
    assert changed_scores["operational_quality"] == pytest.approx(
        base_scores["operational_quality"]
    )
    assert changed_scores["team_experience"] == pytest.approx(0.35)


def test_ingest_score_unsupported_asset_class_is_unavailable(tmp_path: Path) -> None:
    bundle = _write_score_bundle(
        tmp_path,
        name="bundle-unknown-class",
        pdf_replacements=((b"credit", b"banana"),),
    )
    run = _run_score(bundle, tmp_path / "out-unknown-class")
    assert run["final_score"] is None
    assert run["explainability"]["status"] == "unavailable"
    assert run["explainability"]["reason"] == "evidence_backed_score_components_unavailable"
    assert any(w["code"] == "scoring:unavailable" for w in run["warnings"])


def test_ingest_score_ambiguous_aum_is_unavailable(tmp_path: Path) -> None:
    # Two AUM amounts in the submitted document cannot be resolved to one
    # operational input, so production scoring must not guess: it stays
    # unavailable with the minimum-evidence reason even though the workbook
    # evidence is otherwise sufficient.
    bundle = _write_score_bundle(
        tmp_path,
        name="bundle-ambiguous-aum",
        pdf_replacements=((b"$1.2bn", b"$1.2bn and $450m"),),
    )
    run = _run_score(bundle, tmp_path / "out-ambiguous-aum")
    assert run["performance"]["status"] == "available"
    assert run["final_score"] is None
    assert run["explainability"]["status"] == "unavailable"
    assert run["explainability"]["reason"] == "evidence_backed_score_components_unavailable"
    assert any(w["code"] == "scoring:unavailable" for w in run["warnings"])


def test_ingest_score_workbook_change_changes_performance_component(tmp_path: Path) -> None:
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-returns",
            rows=[("2024-01-31", 0.02), ("2024-02-29", 0.03), ("2024-03-31", 0.04)],
        ),
        tmp_path / "out-returns",
    )
    assert _component_scores(changed)["performance_consistency"] != pytest.approx(
        _component_scores(baseline)["performance_consistency"]
    )
    assert changed["final_score"] != pytest.approx(baseline["final_score"])


def test_ingest_score_insufficient_evidence_is_unavailable(tmp_path: Path) -> None:
    bundle = _write_score_bundle(tmp_path, name="bundle-thin", rows=[("2024-01-31", 0.05)])
    run = _run_score(bundle, tmp_path / "out-thin")
    assert run["final_score"] is None
    assert run["explainability"]["status"] == "unavailable"
    assert run["explainability"]["reason"] == "evidence_backed_score_components_unavailable"
    assert any(w["code"] == "scoring:unavailable" for w in run["warnings"])


def test_ingest_score_nonstandard_series_requires_operator_confirmation(
    tmp_path: Path,
) -> None:
    # A missing month makes the series non-standard (backfilled), so the
    # scoring gate blocks scoring until an operator confirms it: the run
    # stays unavailable with the operator-action reason, not a score and
    # not the minimum-evidence reason (evidence is otherwise sufficient).
    rows = [
        ("2024-01-31", 0.12),
        ("2024-03-31", 0.03),
        ("2024-04-30", -0.02),
        ("2024-05-31", 0.04),
    ]
    bundle = _write_score_bundle(tmp_path, name="bundle-gap", rows=rows)
    run = _run_score(bundle, tmp_path / "out-gap")
    assert run["performance"]["status"] == "available"
    assert run["final_score"] is None
    assert run["explainability"]["status"] == "unavailable"
    assert run["explainability"]["reason"] == "operator_confirmation_required"
    assert any(w["code"] == "scoring:unavailable" for w in run["warnings"])


def test_ingest_score_deliberate_break_constants_would_fail(tmp_path: Path) -> None:
    """Constants (smoke ``_score_components``) cannot satisfy these assertions.

    Replacing the derived components with fixed values makes the AUM-driven
    operational change and the workbook-driven performance change disappear.
    """
    baseline = _run_score(_write_score_bundle(tmp_path, name="bundle-base"), tmp_path / "out-base")
    scores = _component_scores(baseline)
    assert scores["operational_quality"] != pytest.approx(0.69)
    assert scores["transparency"] == pytest.approx(0.788)
    assert scores["team_experience"] == pytest.approx(0.35)
    changed = _run_score(
        _write_score_bundle(
            tmp_path,
            name="bundle-aum",
            pdf_replacements=((b"$1.2bn", b"$120m"),),
        ),
        tmp_path / "out-aum",
    )
    assert _component_scores(changed)["operational_quality"] != pytest.approx(
        scores["operational_quality"]
    )


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [("not-a-date", 0.5)],
        [("2024-01-31", True)],
        [("2024-01-31", 0.2), ("2024-01-31", 0.3)],
        [("2024-01-31", "12%")],
    ],
)
def test_ingest_performance_unavailable_for_unparseable_rows(tmp_path: Path, rows) -> None:
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    _write_performance_workbook(bundle_path.parent / "summit_arc_track_record.xlsx", rows)
    output_dir = tmp_path / "output"
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0
    run = json.loads((output_dir / "run.json").read_text())
    assert run["performance"]["status"] == "unavailable"
    assert run["performance"]["monthly"] is None
    assert run["performance"]["metrics"] is None
    assert run["final_score"] is None
    assert any(warning["code"] == "performance:unavailable" for warning in run["warnings"])


def test_ingest_performance_smoke_retains_fixture_returns(v1_smoke_artifacts) -> None:
    assert [point["value"] for point in v1_smoke_artifacts.performance["monthly"]] == [
        0.021,
        -0.012,
        0.018,
        0.006,
        -0.004,
        0.014,
    ]
    assert v1_smoke_artifacts.performance["source"] == "smoke_fixture"
    assert v1_smoke_artifacts.score.final_score == pytest.approx(0.7809)


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


@pytest.mark.parametrize("case", ["no_track_record", "unsupported_headers", "ambiguous_sheets"])
def test_ingest_performance_unavailable_without_unique_supported_table(
    tmp_path: Path, case
) -> None:
    from openpyxl import Workbook

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    bundle = json.loads(bundle_path.read_text())
    if case == "no_track_record":
        for entry in bundle["files"]:
            if entry["role"] == "performance_track_record":
                entry["role"] = "supporting_document"
        bundle_path.write_text(json.dumps(bundle))
    else:
        workbook = Workbook()
        sheet = workbook.active
        if case == "unsupported_headers":
            sheet.append(("month", "profit_dollars"))
            sheet.append(("2024-01-31", 1000))
        else:
            sheet.append(("as_of", "value", "frequency"))
            sheet.append(("2024-01-31", 0.12, "monthly"))
            workbook.copy_worksheet(sheet)
        workbook.save(bundle_path.parent / "summit_arc_track_record.xlsx")
        workbook.close()
    output_dir = tmp_path / "output"
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0
    run = json.loads((output_dir / "run.json").read_text())
    assert run["performance"]["monthly"] is None
    assert run["performance"]["metrics"] is None
    assert run["final_score"] is None
