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
