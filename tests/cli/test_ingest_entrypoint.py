"""Acceptance test for the headless ``inv-man-ingest`` entry point (#473)."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
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
    "validation-queue.json",
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


_PRODUCTION_SMOKE_AUDIT = Path("docs/reports/production_vs_smoke_audit.md")
_V1_SMOKE_SOURCE = Path("src/inv_man_intake/v1_smoke.py")
_SCORING_ENGINE_TESTS = Path("tests/scoring/test_engine.py")
_INGEST_ENTRYPOINT_TESTS = Path("tests/cli/test_ingest_entrypoint.py")
# Reachable smoke_mode / fixed-stand-in inventory IDs from the production audit.
_AUDIT_BOUNDARY_IDS = tuple(f"B{index:02d}" for index in range(1, 21))
_SMOKE_MODE_MARKERS = (
    "smoke_mode = expected_document_ids is not None",
    "content_resolver = None if smoke_mode else filesystem_content_resolver",
    '"source": "smoke_fixture" if smoke_mode else "submitted_workbook"',
    "if not smoke_mode:",
    "if smoke_mode:",
    'analyst_id="analyst_001"',
    "created_at=datetime(2026, 3, 4, 10, 0, tzinfo=UTC)",
    "return _fixture_performance_series()",
    "return _workbook_performance_series(track_record_bytes), None, None",
    'sqlite3.connect(":memory:")',
    "InMemoryDocumentStore()",
    'fallback_name="fixture-fallback"',
    "build_legacy_pdf_fixture_service()",
    'model="deterministic-pdf-parser"',
)
# Classification buckets from docs/reports/production_vs_smoke_audit.md.
_CLASSIFICATION_SUMMARY = {
    "intentional smoke controls (retain)": frozenset(
        {"B02", "B03", "B04", "B05", "B06", "B09", "B14", "B19"}
    ),
    "prevention assertions (tests must hold)": frozenset({"B01", "B07", "B13"}),
    "production path ok / shared policy": frozenset({"B08", "B10", "B17"}),
    "confirmed gaps → product review (no auto-file)": frozenset({"B11"}),
    "superseded review claim": frozenset({"B16"}),
    "architectural / mixed / unknown": frozenset({"B12", "B15", "B18", "B20"}),
}
_EVIDENCE_CLASS_TO_SUMMARY = {
    "prevention assertion": "prevention assertions (tests must hold)",
    "intentional smoke control": "intentional smoke controls (retain)",
    "intentional smoke control (boundary)": "intentional smoke controls (retain)",
    "intentional production path (post-#1019 seam)": "production path ok / shared policy",
    "intentional shared policy": "production path ok / shared policy",
    "confirmed production gap": "confirmed gaps → product review (no auto-file)",
    "production path repaired by #1018 / #1034": "production path ok / shared policy",
    "architectural seam": "architectural / mixed / unknown",
    "intentional / prevention": "prevention assertions (tests must hold)",
    "mixed / historical corpus seam": "architectural / mixed / unknown",
    "superseded review claim": "superseded review claim",
    "intentional / ocr-fallback partial": "architectural / mixed / unknown",
}


def _parse_audit_boundary_rows(audit: str) -> dict[str, dict[str, str]]:
    """Parse reachable-branch table rows keyed by boundary ID."""
    section = audit.split("## Reachable branches and fixed assumptions", maxsplit=1)[1].split(
        "## Classification summary",
        maxsplit=1,
    )[0]
    rows: dict[str, dict[str, str]] = {}
    for line in section.splitlines():
        if not line.startswith("| B"):
            continue
        columns = [column.strip() for column in line.split("|")]
        # split("|") yields leading/trailing empties around markdown cells.
        cells = columns[1:-1] if columns and columns[0] == "" else columns
        if len(cells) < 8:
            continue
        boundary_id = cells[0]
        rows[boundary_id] = {
            "source": cells[1],
            "condition": cells[2],
            "production_contract": cells[3],
            "smoke_behavior": cells[4],
            "evidence_class": cells[5].replace("**", "").strip(),
            "classification_evidence": cells[6],
            "disposition": cells[7],
        }
    return rows


def test_production_smoke_audit_inventories_reachable_smoke_mode_branches() -> None:
    """Inventory guard: audit enumerates every reachable smoke_mode / fixed stand-in."""
    source = _V1_SMOKE_SOURCE.read_text(encoding="utf-8")
    audit = _PRODUCTION_SMOKE_AUDIT.read_text(encoding="utf-8")

    for marker in _SMOKE_MODE_MARKERS:
        assert marker in source, f"missing reachable inventory marker in v1_smoke.py: {marker}"
    for boundary_id in _AUDIT_BOUNDARY_IDS:
        assert f"| {boundary_id} |" in audit, f"audit missing boundary {boundary_id}"

    # Review-time document_ids[0]/[1] indexing is superseded by role/extension selection.
    assert "document_ids[0]" not in source
    assert "document_ids[1]" not in source
    assert "_select_extraction_documents" in source
    assert "PRIMARY_EXTENSIONS" in source


def test_production_smoke_audit_classifies_boundaries_with_existing_tests() -> None:
    """Classify each inventory boundary using CLI + scoring engine evidence.

    Separates intentional smoke controls from confirmed gaps and unknowns without
    filing follow-up issues. Cited ``test_*`` names must exist in the declared
    owner test modules from the issue scope.
    """
    audit = _PRODUCTION_SMOKE_AUDIT.read_text(encoding="utf-8")
    entrypoint_tests = _INGEST_ENTRYPOINT_TESTS.read_text(encoding="utf-8")
    engine_tests = _SCORING_ENGINE_TESTS.read_text(encoding="utf-8")
    rows = _parse_audit_boundary_rows(audit)

    assert set(rows) == set(_AUDIT_BOUNDARY_IDS)

    classified: dict[str, set[str]] = {label: set() for label in _CLASSIFICATION_SUMMARY}
    for boundary_id, row in rows.items():
        evidence_class = row["evidence_class"].lower()
        assert (
            evidence_class in _EVIDENCE_CLASS_TO_SUMMARY
        ), f"{boundary_id} has unknown evidence class {row['evidence_class']!r}"
        summary_label = _EVIDENCE_CLASS_TO_SUMMARY[evidence_class]
        classified[summary_label].add(boundary_id)

        evidence = row["classification_evidence"]
        disposition = row["disposition"].lower()
        assert evidence.strip(), f"{boundary_id} missing classification evidence"
        assert row["production_contract"].strip(), f"{boundary_id} missing production contract"
        assert disposition.strip(), f"{boundary_id} missing disposition"

        if evidence_class == "confirmed production gap":
            assert "no auto-filed" in disposition or "return for human" in disposition

        # Scope requires classification via these two test modules for smoke/score seams.
        if boundary_id in {
            "B01",
            "B02",
            "B04",
            "B05",
            "B06",
            "B07",
            "B10",
            "B11",
            "B13",
            "B14",
            "B16",
        }:
            assert "test_" in evidence, f"{boundary_id} must cite an existing CLI test"
        if boundary_id in {"B08", "B09"}:
            assert "tests/scoring/test_engine.py" in evidence or "test_engine.py" in evidence
            assert "test_ingest_" in evidence or "test_ingest_entrypoint.py" in evidence

        for token in evidence.replace("`", " ").replace(",", " ").replace("(", " ").split():
            if not token.startswith("test_"):
                continue
            name = token.rstrip(").,;")
            present = name in entrypoint_tests or name in engine_tests
            assert present, f"{boundary_id} cites missing test {name}"

    for label, expected_ids in _CLASSIFICATION_SUMMARY.items():
        assert classified[label] == expected_ids, f"summary drift for {label}"

    human_section = audit.split("## Uncovered items returned for human review", maxsplit=1)[1]
    assert "No automatic follow-up issues are created" in human_section
    for gap_id in ("B10", "B11", "B15", "B18"):
        assert gap_id in human_section, f"human-review section missing {gap_id}"


def test_run_pipeline_invokes_core_without_smoke_document_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production must never pass ``expected_document_ids`` (smoke_mode gate)."""
    from inv_man_intake import run as run_module
    from inv_man_intake import v1_smoke

    observed: list[tuple[str, ...] | None] = []
    original = v1_smoke._run_pipeline_core

    def recording_core(**kwargs):
        observed.append(kwargs.get("expected_document_ids"))
        return original(**kwargs)

    monkeypatch.setattr(run_module, "_run_pipeline_core", recording_core)
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    output_dir = tmp_path / "out"
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0
    assert observed == [None]


def test_run_pipeline_disables_remote_tracing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production ``run_pipeline`` must keep tracing local (audit B13)."""
    from inv_man_intake import run as run_module
    from inv_man_intake import v1_smoke

    observed: list[bool] = []
    original = v1_smoke._run_pipeline_core

    def recording_core(**kwargs):
        observed.append(bool(kwargs.get("allow_remote_tracing", True)))
        return original(**kwargs)

    monkeypatch.setattr(run_module, "_run_pipeline_core", recording_core)
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    assert main([str(bundle_path), "--out", str(tmp_path / "out")]) == 0
    assert observed == [False]


def test_production_performance_source_deliberate_smoke_fixture_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deliberate-break gate: mislabeling production performance as smoke_fixture fails.

    Mutating the core result to ``smoke_fixture`` makes the prevention assertion
    fail; restoring ``submitted_workbook`` passes (audit B07 / acceptance mutation).
    """
    from dataclasses import replace

    from inv_man_intake import run as run_module
    from inv_man_intake import v1_smoke

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    original = v1_smoke._run_pipeline_core

    def mislabeled_core(**kwargs):
        artifacts = original(**kwargs)
        bad_performance = dict(artifacts.performance)
        bad_performance["source"] = "smoke_fixture"
        return replace(artifacts, performance=bad_performance)

    monkeypatch.setattr(run_module, "_run_pipeline_core", mislabeled_core)
    broken_dir = tmp_path / "broken"
    assert main([str(bundle_path), "--out", str(broken_dir)]) == 0
    broken = json.loads((broken_dir / "run.json").read_text(encoding="utf-8"))
    with pytest.raises(AssertionError):
        assert broken["performance"]["source"] == "submitted_workbook"

    monkeypatch.setattr(run_module, "_run_pipeline_core", original)
    restored_dir = tmp_path / "restored"
    assert main([str(bundle_path), "--out", str(restored_dir)]) == 0
    restored = json.loads((restored_dir / "run.json").read_text(encoding="utf-8"))
    assert restored["performance"]["source"] == "submitted_workbook"


def test_production_queue_assignment_is_unowned_and_uses_live_clock(tmp_path: Path) -> None:
    """Retain the production queue handoff delivered by #1018 / #1034."""
    from inv_man_intake import v1_smoke
    from inv_man_intake.run import run_pipeline

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    package_id = json.loads(bundle_path.read_text(encoding="utf-8"))["package_id"]
    artifacts = v1_smoke._run_pipeline_core(
        fixture_root=bundle_path.parent,
        intake_bundle_file=bundle_path.name,
        package_id=package_id,
        content_root=bundle_path.parent,
        allow_remote_tracing=False,
    )
    assert artifacts.queue_assignment is not None
    assert artifacts.queue_assignment.owner_id is None
    assert artifacts.queue_assignment.state == "pending_triage"
    assert artifacts.queue_assignment.package_id == package_id
    assert (
        datetime.fromisoformat(artifacts.queue_assignment.created_at).date()
        == datetime.now(UTC).date()
    )
    # Keep the same behavior exercised on the headless path.
    run_pipeline(bundle_path, output_dir=tmp_path / "out")


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


@pytest.mark.parametrize("reverse", [False, True], ids=["primary-first", "workbook-first"])
def test_ingest_secondary_boundary_uses_submitted_workbook_bytes_and_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reverse: bool
) -> None:
    """B05: production secondary extraction receives submitted content and identity."""
    from inv_man_intake import v1_smoke

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    payload["package_id"] = "pkg_submitted_secondary"
    workbook_name = "submitted-track-record.xlsx"
    for entry in payload["files"]:
        if entry["role"] == "performance_track_record":
            (bundle_path.parent / entry["file_name"]).unlink()
            entry["file_name"] = workbook_name
    workbook_path = bundle_path.parent / workbook_name
    _write_performance_workbook(workbook_path, [("2024-01-31", 0.12), ("2024-02-29", -0.07)])
    submitted_bytes = workbook_path.read_bytes()
    if reverse:
        payload["files"].reverse()
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    workbook_index = next(
        index for index, entry in enumerate(payload["files"]) if entry["file_name"] == workbook_name
    )
    expected_id = f"{payload['package_id']}:doc:{workbook_index}"
    observed: list[tuple[str, bytes]] = []
    original = v1_smoke._run_secondary_extraction_boundary_smoke

    def recording_secondary(**kwargs):
        observed.append((kwargs["source_doc_id"], kwargs["content"]))
        return original(**kwargs)

    monkeypatch.setattr(v1_smoke, "_run_secondary_extraction_boundary_smoke", recording_secondary)
    assert main([str(bundle_path), "--out", str(tmp_path / "out")]) == 0
    assert observed == [(expected_id, submitted_bytes)]


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


@pytest.mark.parametrize("accepted", [False, True], ids=["escalating", "accepted-policy"])
def test_ingest_queue_artifact_reloads_real_outcomes_and_manifest(
    tmp_path: Path, accepted: bool
) -> None:
    import hashlib

    from inv_man_intake.validation_queue_api import ValidationQueueQuery, list_validation_queue
    from inv_man_intake.workflow_validation import (
        claim_for_analyst_triage,
        load_validation_queue,
        load_validation_queue_rows,
        queue_replay_key,
        transition_state,
        write_validation_queue,
    )

    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    output = tmp_path / "output"
    args = [str(bundle), "--out", str(output)]
    if accepted:
        # A real caller-supplied policy accepts AUM(.72) while leaving the fixture defaults alone.
        policy = tmp_path / "thresholds.yaml"
        policy.write_text(
            Path("config/extraction_thresholds.yaml")
            .read_text()
            .replace("key_field_confidence_min: 0.75", "key_field_confidence_min: 0.70")
        )
        args += ["--threshold-config", str(policy)]
    started = datetime.now(UTC).replace(microsecond=0)
    assert main(args) == 0
    run = json.loads((output / "run.json").read_text())
    queue_file = output / "validation-queue.json"
    records = load_validation_queue(queue_file)
    page = list_validation_queue(
        load_validation_queue_rows(queue_file),
        query=ValidationQueueQuery(package_id=run["inputs"]["package_id"]),
    )
    assert bool(run["escalation_state"]["escalate"]) is (not accepted)
    assert page.total == len(records) == (0 if accepted else 1)
    assert (
        list_validation_queue(
            load_validation_queue_rows(queue_file),
            query=ValidationQueueQuery(package_id="other-package"),
        ).total
        == 0
    )
    assert "validation-queue.json" in run["artifact_refs"]
    entry = next(
        row
        for row in json.loads((output / "manifest.json").read_text())["artifacts"]
        if row["name"] == "validation-queue.json"
    )
    assert entry["sha256"] == hashlib.sha256(queue_file.read_bytes()).hexdigest()
    assert entry["bytes"] == queue_file.stat().st_size
    for item in records:
        assert item.owner_id is item.owner_role is None
        assert item.state == "pending_triage" and item.events == ()
        assert item.escalation_reason == run["escalation_state"]["reason"]
        assert item.item_id == queue_replay_key(item.package_id, item.escalation_reason)
        assert datetime.fromisoformat(item.created_at).tzinfo is not None
        assert started <= datetime.fromisoformat(item.created_at) <= datetime.now(UTC)
    assert main(args) == 0
    assert [item.item_id for item in load_validation_queue(queue_file)] == [
        item.item_id for item in records
    ]
    replayed_run = json.loads((output / "run.json").read_text())
    assert replayed_run["run_id"] != run["run_id"]
    if records:
        claimed = claim_for_analyst_triage(
            load_validation_queue(queue_file)[0], analyst_id="explicit-owner", note="Review started"
        )
        handoff = tmp_path / "reviewed-queue.json"
        write_validation_queue(handoff, [claimed])
        reloaded_claim = load_validation_queue(handoff)[0]
        assert reloaded_claim == claimed
        completed = transition_state(
            reloaded_claim,
            actor_id="explicit-owner",
            actor_role="analyst",
            to_state="completed",
            note="Evidence verified",
        )
        write_validation_queue(handoff, [completed])
        assert load_validation_queue(handoff) == (completed,)
        assert [event.action for event in completed.events] == ["claim", "state_transition"]
        assert [event.note for event in completed.events] == ["Review started", "Evidence verified"]
        completed_page = list_validation_queue(
            load_validation_queue_rows(handoff),
            query=ValidationQueueQuery(package_id=completed.package_id, states=("completed",)),
        )
        assert completed_page.total == 1
        assert completed_page.items[0].owner_id == "explicit-owner"


@pytest.mark.parametrize("completed", [False, True], ids=["claimed", "completed"])
def test_ingest_queue_replay_preserves_saved_review_by_requiring_new_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], completed: bool
) -> None:
    from inv_man_intake.workflow_validation import (
        claim_for_analyst_triage,
        load_validation_queue,
        transition_state,
        write_validation_queue,
    )

    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    output = tmp_path / "output"
    args = [str(bundle), "--out", str(output)]
    assert main(args) == 0
    queue_file = output / "validation-queue.json"
    reviewed = claim_for_analyst_triage(
        load_validation_queue(queue_file)[0], analyst_id="explicit-owner", note="Review started"
    )
    if completed:
        reviewed = transition_state(
            reviewed, actor_id="explicit-owner", actor_role="analyst", to_state="completed"
        )
    write_validation_queue(queue_file, [reviewed])
    saved_files = {path.name: path.read_bytes() for path in output.iterdir()}

    assert main(args) == 1
    assert "queue review progress" in capsys.readouterr().err
    assert load_validation_queue(queue_file) == (reviewed,)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == saved_files

    # A new run directory remains usable without discarding the previous review.
    assert main([str(bundle), "--out", str(tmp_path / "new-output")]) == 0
    assert load_validation_queue(queue_file) == (reviewed,)
