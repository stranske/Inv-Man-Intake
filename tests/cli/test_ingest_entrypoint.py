"""Acceptance test for the headless ``inv-man-ingest`` entry point (#473)."""

from __future__ import annotations

import ast
import json
import re
import shutil
from calendar import monthrange
from collections import Counter
from datetime import UTC, date, datetime
from itertools import permutations
from pathlib import Path

import pytest

from inv_man_intake.cli.ingest import main

_BUNDLE = "tests/fixtures/intake/pdf_primary_mixed_bundle.json"
_FIXTURE_EXTRACTION = Path("tests/fixtures/extraction")
# Production PDFs route to Doc-Lineage, which needs a conforming PDF; the
# historical pseudo-PDF of the same name stays the smoke-only pdf-primary corpus.
_PRODUCTION_FIXTURE_SOURCES = {
    "summit_arc_investment_update.pdf": "summit_arc_investment_update_conforming.pdf",
}
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


def _production_fixture(file_name: str) -> Path:
    return _FIXTURE_EXTRACTION / _PRODUCTION_FIXTURE_SOURCES.get(file_name, file_name)


def _write_review_policy(tmp_path: Path) -> Path:
    """Explicit policy that escalates the reference run for analyst review.

    Doc-Lineage scores every parsed field 0.82, which the default policy accepts;
    escalation must come from caller policy rather than a parser's fixed AUM score.
    """
    policy = tmp_path / "review-thresholds.yaml"
    policy.write_text(
        Path("config/extraction_thresholds.yaml")
        .read_text(encoding="utf-8")
        .replace("key_field_confidence_min: 0.75", "key_field_confidence_min: 0.85"),
        encoding="utf-8",
    )
    return policy


def _write_external_layout_bundle(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    bundle_payload = _minimal_external_bundle_payload()
    for entry in bundle_payload["files"]:
        source = _production_fixture(entry["file_name"])
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
    policy = _write_review_policy(tmp_path)
    assert (
        main([str(bundle_path), "--out", str(output_dir), "--threshold-config", str(policy)]) == 0
    )

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
    '("fixture-fallback", _fixture_id_only_extractor)',
    "(INCOMPLETE_EXTRACTION_DISPOSITION, _incomplete_extraction_extractor)",
    "build_legacy_pdf_fixture_service()",
    "build_pyodide_light_service(primary_file_name, require_doc_lineage=True)",
    'model="deterministic-pdf-parser"',
)
# One entry per conditional, including repeated predicates in the same function.
# Boundary IDs tie both statement and expression branches to the audit table.
_AUDITED_SMOKE_BRANCHES = (
    ("_run_pipeline_core", "IfExp", "smoke_mode", "B02"),
    ("_run_pipeline_core", "If", "expected_document_ids is None", "B03"),
    ("_run_pipeline_core", "If", "smoke_mode", "B05"),
    ("_run_pipeline_core", "IfExp", "smoke_mode", "B07"),
    ("_run_pipeline_core", "If", "smoke_mode", "B10"),
    ("_run_pipeline_core", "If", "not smoke_mode", "B08"),
    ("_run_pipeline_core", "If", "smoke_mode", "B09"),
    ("_run_pipeline_core", "IfExp", "smoke_mode", "B10"),
    ("_pipeline_document_bytes", "If", "smoke_mode", "B04"),
    ("_resolve_performance_series", "If", "smoke_mode", "B06"),
    ("_run_extraction_smoke", "If", "smoke_mode", "B15"),
    ("_run_extraction_smoke", "IfExp", "smoke_mode", "B18"),
)
# Classification buckets from docs/reports/production_vs_smoke_audit.md.
_CLASSIFICATION_SUMMARY = {
    "intentional smoke controls (retain)": frozenset(
        {"B02", "B03", "B04", "B05", "B06", "B09", "B14", "B19"}
    ),
    "prevention assertions (tests must hold)": frozenset({"B01", "B07", "B13"}),
    "production path ok / shared policy": frozenset({"B08", "B10", "B15", "B17", "B18"}),
    "confirmed gaps → product review (no auto-file)": frozenset({"B11"}),
    "superseded review claim": frozenset({"B16"}),
    "architectural / mixed / unknown": frozenset({"B12", "B20"}),
}
_EVIDENCE_CLASS_TO_SUMMARY = {
    "prevention assertion": "prevention assertions (tests must hold)",
    "intentional smoke control": "intentional smoke controls (retain)",
    "intentional smoke control (boundary)": "intentional smoke controls (retain)",
    "intentional production path (post-#1019 seam)": "production path ok / shared policy",
    "intentional shared policy": "production path ok / shared policy",
    "confirmed production gap": "confirmed gaps → product review (no auto-file)",
    "partially repaired by #1084 (benchmark gap remains)": (
        "confirmed gaps → product review (no auto-file)"
    ),
    "production path repaired by #1018 / #1034": "production path ok / shared policy",
    "production path repaired by #1083": "production path ok / shared policy",
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


def _assert_audited_smoke_branches(source: str) -> None:
    branches: Counter[tuple[str, str, str]] = Counter()
    for function in ast.parse(source).body:
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if not isinstance(node, (ast.If, ast.IfExp)):
                continue
            if any(
                isinstance(name, ast.Name) and name.id in {"smoke_mode", "expected_document_ids"}
                for name in ast.walk(node.test)
            ):
                branches[(function.name, type(node).__name__, ast.unparse(node.test))] += 1
    expected = Counter(
        (function, kind, predicate) for function, kind, predicate, _ in _AUDITED_SMOKE_BRANCHES
    )
    assert branches == expected, (
        "smoke branch inventory changed; update the audit disposition: "
        f"added={branches - expected}, removed={expected - branches}"
    )


def test_production_smoke_audit_inventories_reachable_smoke_mode_branches() -> None:
    """Inventory guard: audit enumerates every reachable smoke_mode / fixed stand-in."""
    source = _V1_SMOKE_SOURCE.read_text(encoding="utf-8")
    audit = _PRODUCTION_SMOKE_AUDIT.read_text(encoding="utf-8")

    _assert_audited_smoke_branches(source)
    assert {boundary_id for *_, boundary_id in _AUDITED_SMOKE_BRANCHES} <= set(_AUDIT_BOUNDARY_IDS)
    for marker in _SMOKE_MODE_MARKERS:
        assert marker in source, f"missing reachable inventory marker in v1_smoke.py: {marker}"
    for boundary_id in _AUDIT_BOUNDARY_IDS:
        assert f"| {boundary_id} |" in audit, f"audit missing boundary {boundary_id}"

    # Review-time document_ids[0]/[1] indexing is superseded by role/extension selection.
    assert "document_ids[0]" not in source
    assert "document_ids[1]" not in source
    assert "_select_extraction_documents" in source
    assert "PRIMARY_EXTENSIONS" in source


@pytest.mark.parametrize(
    "new_branch",
    ["if smoke_mode:\n        pass", "unreviewed_value = None if smoke_mode else False"],
    ids=["statement", "expression"],
)
def test_smoke_branch_inventory_rejects_unreviewed_conditionals(new_branch: str) -> None:
    source = _V1_SMOKE_SOURCE.read_text(encoding="utf-8")
    discriminator = "smoke_mode = expected_document_ids is not None"
    mutated = source.replace(discriminator, f"{discriminator}\n    {new_branch}", 1)

    # Existing source markers survive this regression; the complete inventory must fail.
    with pytest.raises(AssertionError, match="smoke branch inventory changed"):
        _assert_audited_smoke_branches(mutated)
    _assert_audited_smoke_branches(source)


def _defined_test_names(source: str) -> set[str]:
    return {
        node.name
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _assert_audit_test_evidence(
    boundary_id: str, evidence: str, entrypoint_names: set[str], engine_names: set[str]
) -> None:
    # Module paths are context, not citations of individual test functions.
    cited_names = set(re.findall(r"\btest_[A-Za-z0-9_]+\b(?!\.py\b)", evidence))
    missing = cited_names - (entrypoint_names | engine_names)
    assert not missing, f"{boundary_id} cites missing tests: {sorted(missing)}"
    if boundary_id in {
        "B01",
        "B02",
        "B04",
        "B05",
        "B06",
        "B07",
        "B08",
        "B09",
        "B10",
        "B11",
        "B13",
        "B14",
        "B15",
        "B16",
        "B18",
    }:
        assert cited_names & entrypoint_names, f"{boundary_id} must cite an existing CLI test"
    if boundary_id in {"B08", "B09"}:
        assert cited_names & engine_names, f"{boundary_id} must cite an existing scoring test"


@pytest.mark.parametrize(
    "evidence",
    ["test_", "tests/cli/test_ingest_entrypoint.py", "test_ingest", "test_missing"],
)
def test_audit_test_evidence_rejects_missing_or_partial_citations(evidence: str) -> None:
    source = "def test_ingest_full(): pass\n# test_missing\n"
    with pytest.raises(AssertionError):
        _assert_audit_test_evidence("B01", evidence, _defined_test_names(source), set())


def test_audit_test_evidence_accepts_exact_names_with_punctuation() -> None:
    _assert_audit_test_evidence(
        "B08",
        "tests/cli/test_ingest_entrypoint.py (`test_ingest_full`): test_engine_full;",
        {"test_ingest_full"},
        {"test_engine_full"},
    )


@pytest.mark.parametrize("evidence", ["test_ingest_full", "test_engine_full"])
def test_audit_scoring_evidence_requires_both_owner_modules(evidence: str) -> None:
    with pytest.raises(AssertionError):
        _assert_audit_test_evidence("B08", evidence, {"test_ingest_full"}, {"test_engine_full"})


def test_production_smoke_audit_classifies_boundaries_with_existing_tests() -> None:
    """Classify each inventory boundary using CLI + scoring engine evidence.

    Separates intentional smoke controls from confirmed gaps and unknowns without
    filing follow-up issues. Cited ``test_*`` names must exist in the declared
    owner test modules from the issue scope.
    """
    audit = _PRODUCTION_SMOKE_AUDIT.read_text(encoding="utf-8")
    entrypoint_tests = _defined_test_names(_INGEST_ENTRYPOINT_TESTS.read_text(encoding="utf-8"))
    engine_tests = _defined_test_names(_SCORING_ENGINE_TESTS.read_text(encoding="utf-8"))
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

        if evidence_class in {
            "confirmed production gap",
            "partially repaired by #1084 (benchmark gap remains)",
        }:
            assert "no auto-filed" in disposition or "return for human" in disposition

        _assert_audit_test_evidence(boundary_id, evidence, entrypoint_tests, engine_tests)

    for label, expected_ids in _CLASSIFICATION_SUMMARY.items():
        assert classified[label] == expected_ids, f"summary drift for {label}"
    # #1084: B11's deck comparison is repaired; only the benchmark gap stays with a human.
    assert rows["B11"]["evidence_class"] == "partially repaired by #1084 (benchmark gap remains)"
    assert (
        "test_production_conflict_over_5pct_emits_performance_conflict_queue_item"
        in rows["B11"]["classification_evidence"]
    )

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


def _assert_production_performance_source(run: dict) -> None:
    assert (
        run["performance"]["source"] == "submitted_workbook"
    ), "production performance must use the submitted workbook"


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
    # Exercise the same prevention assertion used by the external-layout test.
    with pytest.raises(
        AssertionError, match="production performance must use the submitted workbook"
    ):
        _assert_production_performance_source(broken)

    monkeypatch.setattr(run_module, "_run_pipeline_core", original)
    restored_dir = tmp_path / "restored"
    assert main([str(bundle_path), "--out", str(restored_dir)]) == 0
    restored = json.loads((restored_dir / "run.json").read_text(encoding="utf-8"))
    _assert_production_performance_source(restored)


def test_production_queue_assignment_is_unowned_and_uses_live_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retain the production queue handoff delivered by #1018 / #1034."""
    from inv_man_intake import v1_smoke, workflow_validation
    from inv_man_intake.extraction.confidence import load_threshold_config
    from inv_man_intake.run import run_pipeline

    current_time = datetime(2031, 7, 9, 14, 23, 11, tzinfo=UTC)

    class ControlledDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC, "queue creation must request a UTC timestamp"
            return current_time

    monkeypatch.setattr(workflow_validation, "datetime", ControlledDateTime)
    bundle_path = _write_external_layout_bundle(tmp_path / "bundle-root")
    package_id = json.loads(bundle_path.read_text(encoding="utf-8"))["package_id"]
    policy = _write_review_policy(tmp_path)
    artifacts = v1_smoke._run_pipeline_core(
        fixture_root=bundle_path.parent,
        intake_bundle_file=bundle_path.name,
        package_id=package_id,
        threshold_config=load_threshold_config(policy),
        content_root=bundle_path.parent,
        allow_remote_tracing=False,
    )
    assert artifacts.queue_assignment is not None
    assert artifacts.queue_assignment.owner_id is None
    assert artifacts.queue_assignment.owner_role is None
    assert artifacts.queue_assignment.state == "pending_triage"
    assert artifacts.queue_assignment.package_id == package_id
    assert datetime.fromisoformat(artifacts.queue_assignment.created_at) == current_time
    assert artifacts.queue_assignment.updated_at == artifacts.queue_assignment.created_at

    # Advance within the same day: checking only the date would miss a fixed clock.
    current_time = datetime(2031, 7, 9, 14, 23, 37, tzinfo=UTC)
    output_dir = tmp_path / "out"
    run_pipeline(bundle_path, output_dir=output_dir, threshold_config_path=policy)
    (saved_item,) = workflow_validation.load_validation_queue(output_dir / "validation-queue.json")
    assert saved_item.owner_id is saved_item.owner_role is None
    assert saved_item.state == "pending_triage"
    assert saved_item.item_id == artifacts.queue_assignment.item_id
    assert datetime.fromisoformat(saved_item.created_at) == current_time
    assert saved_item.updated_at == saved_item.created_at
    assert saved_item.created_at != artifacts.queue_assignment.created_at


@pytest.mark.parametrize(
    "primary", ["summit_arc_investment_update.pdf", "harborline_strategy_review.pptx"]
)
def test_ingest_primary_only_pdf_and_pptx(tmp_path, monkeypatch, primary):
    from inv_man_intake import v1_smoke

    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle.read_text())
    entry = payload["files"][0]
    entry["file_name"] = primary
    shutil.copyfile(_production_fixture(primary), bundle.parent / primary)
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


def _compressed_two_page_pdf() -> bytes:
    from io import BytesIO

    from reportlab.pdfgen import canvas

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pageCompression=1, invariant=1)
    pdf.drawString(72, 720, "Strategy Asset Class: credit")
    pdf.drawString(72, 700, "Management Fee: 1.25%")
    pdf.showPage()
    pdf.drawString(72, 720, "AUM: $1.2bn")
    pdf.drawString(72, 700, "Net Return 1Y: 8.4%")
    pdf.drawString(72, 680, "Strategy: Summit Arc Credit")
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


def _forbid_legacy_pdf_fixture_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from inv_man_intake import v1_smoke

    def legacy_fixture_service():
        raise AssertionError("production PDFs must not use build_legacy_pdf_fixture_service")

    monkeypatch.setattr(v1_smoke, "build_legacy_pdf_fixture_service", legacy_fixture_service)


def test_production_pdf_routes_to_doc_lineage_not_legacy_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B15: production .pdf extraction uses Doc-Lineage, never the pseudo-PDF parser."""
    from inv_man_intake.extraction.providers.pdf_primary import PdfPrimaryExtractionProvider

    _forbid_legacy_pdf_fixture_service(monkeypatch)
    pdf_bytes = _compressed_two_page_pdf()
    # Compressed content streams carry no literal text the legacy parser can read.
    assert b"/FlateDecode" in pdf_bytes
    assert PdfPrimaryExtractionProvider().extract("probe", pdf_bytes).fields == ()
    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    (bundle.parent / "summit_arc_investment_update.pdf").write_bytes(pdf_bytes)

    output = tmp_path / "out"
    assert main([str(bundle), "--out", str(output)]) == 0

    run = json.loads((output / "run.json").read_text(encoding="utf-8"))
    fields = {field["key"]: field for field in run["fields"]}
    assert not any(
        field["key"] == "strategy.name" and field["source_page"] == 1 for field in run["fields"]
    )
    expected = {
        "strategy.asset_class": ("credit", 1),
        "terms.management_fee": ("1.25%", 1),
        "operations.aum": ("$1.2bn", 2),
        "performance.net_return_1y": ("8.4%", 2),
        "strategy.name": ("Summit Arc Credit", 2),
    }
    for key, (value, page) in expected.items():
        assert fields[key]["value"] == value
        assert fields[key]["source_page"] == page
        assert fields[key]["location"]["source_page"] == page
        assert fields[key]["method"] == "doc-lineage:text_layer"
        assert run["provenance"]["evidence"][key]["source_page"] == page


def test_production_pdf_missing_doc_lineage_extra_fails_visibly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B15: an absent extra is a named dependency error, not a pdf-primary downgrade."""
    from inv_man_intake.extraction import MissingExtractionDependencyError
    from inv_man_intake.extraction.providers import doc_lineage_adapter, pdf_primary

    class AbsentDocLineage:
        def __init__(self) -> None:
            raise ModuleNotFoundError("No module named 'doc_lineage'", name="doc_lineage")

    class ForbiddenPdfPrimary:
        def __init__(self) -> None:
            raise AssertionError("production must not downgrade to pdf-primary")

    _forbid_legacy_pdf_fixture_service(monkeypatch)
    monkeypatch.setattr(doc_lineage_adapter, "DocLineageExtractionProvider", AbsentDocLineage)
    monkeypatch.setattr(pdf_primary, "PdfPrimaryExtractionProvider", ForbiddenPdfPrimary)
    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    output = tmp_path / "out"

    with pytest.raises(MissingExtractionDependencyError, match="extraction-doc-lineage") as caught:
        main([str(bundle), "--out", str(output)])

    assert caught.value.package == "doc_lineage"
    assert caught.value.file_name == "summit_arc_investment_update.pdf"
    assert not (output / "run.json").exists()


def test_production_pdf_broken_doc_lineage_install_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B15: a transitive import failure inside Doc-Lineage is not relabelled as missing."""
    from inv_man_intake.extraction import MissingExtractionDependencyError
    from inv_man_intake.extraction.providers import doc_lineage_adapter

    class BrokenDocLineage:
        def __init__(self) -> None:
            raise ModuleNotFoundError("No module named 'pypdf'", name="pypdf")

    _forbid_legacy_pdf_fixture_service(monkeypatch)
    monkeypatch.setattr(doc_lineage_adapter, "DocLineageExtractionProvider", BrokenDocLineage)
    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    output = tmp_path / "out"

    with pytest.raises(ModuleNotFoundError) as caught:
        main([str(bundle), "--out", str(output)])

    assert caught.value.name == "pypdf"
    assert not isinstance(caught.value, MissingExtractionDependencyError)
    assert not (output / "run.json").exists()


def test_production_incomplete_extraction_routes_to_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """B18: unresolved production extraction is an attributable review outcome, not id-only."""
    from inv_man_intake import v1_smoke
    from inv_man_intake.observability import Tracer, new_trace_context

    _forbid_legacy_pdf_fixture_service(monkeypatch)
    # The historical pseudo-PDF has no font resources: Doc-Lineage reads no page text.
    unreadable = (_FIXTURE_EXTRACTION / "summit_arc_investment_update.pdf").read_bytes()
    bundle = _write_external_layout_bundle(tmp_path / "bundle")
    (bundle.parent / "summit_arc_investment_update.pdf").write_bytes(unreadable)
    output = tmp_path / "out"

    assert main([str(bundle), "--out", str(output)]) == 1
    err = capsys.readouterr().err
    assert "incomplete-extraction" in err
    assert "Doc-Lineage left unreadable PDF pages" in err
    assert not (output / "run.json").exists()

    with pytest.raises(v1_smoke.ExtractionReviewRequiredError) as caught:
        v1_smoke._run_extraction_smoke(
            tracer=Tracer(enabled=False),
            trace_context=new_trace_context(),
            source_doc_id="doc-unreadable",
            primary_file_name="manager_update.pdf",
            content=unreadable,
            correlation_id="corr-unreadable",
            smoke_mode=False,
        )
    failure = caught.value
    assert failure.disposition == v1_smoke.INCOMPLETE_EXTRACTION_DISPOSITION
    assert failure.file_name == "manager_update.pdf"
    assert failure.escalation_route == "ops_review"
    assert failure.errors[0].startswith("pyodide-light: Doc-Lineage left unreadable PDF pages")
    assert failure.errors[1].startswith("incomplete-extraction: no production fallback")
    assert "doc-unreadable" in failure.errors[1]


@pytest.mark.parametrize(
    "primary", ["summit_arc_investment_update.pdf", "harborline_strategy_review.pptx"]
)
@pytest.mark.parametrize("reverse", [False, True], ids=["primary-first", "workbook-first"])
@pytest.mark.parametrize("explicit_id", [False, True], ids=["generated-id", "submitted-id"])
def test_ingest_primary_uses_submitted_bytes_filename_and_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, primary: str, reverse: bool, explicit_id: bool
) -> None:
    """B04/B16: renamed primary submissions retain their content and registered identity."""
    from inv_man_intake import v1_smoke

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    payload["package_id"] = "pkg_submitted_primary"
    primary_entry = next(entry for entry in payload["files"] if entry["file_name"].endswith(".pdf"))
    (bundle_path.parent / primary_entry["file_name"]).unlink()
    submitted_name = f"submitted-manager-update{Path(primary).suffix}"
    submitted_bytes = _production_fixture(primary).read_bytes() + b"\nsubmitted-primary-marker\n"
    primary_entry["file_name"] = submitted_name
    if explicit_id:
        primary_entry["document_id"] = "external-manager-update-902"
    (bundle_path.parent / submitted_name).write_bytes(submitted_bytes)
    if reverse:
        payload["files"].reverse()
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    primary_index = payload["files"].index(primary_entry)
    expected_id = primary_entry.get("document_id", f"{payload['package_id']}:doc:{primary_index}")
    observed: list[tuple[str, str, bytes]] = []
    original = v1_smoke._run_extraction_smoke

    def recording_primary(**kwargs):
        observed.append((kwargs["source_doc_id"], kwargs["primary_file_name"], kwargs["content"]))
        return original(**kwargs)

    monkeypatch.setattr(v1_smoke, "_run_extraction_smoke", recording_primary)
    output_dir = tmp_path / "out"
    assert main([str(bundle_path), "--out", str(output_dir)]) == 0
    assert observed == [(expected_id, submitted_name, submitted_bytes)]
    run = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run["fields"]
    assert {field["source_doc_id"] for field in run["fields"]} == {expected_id}
    assert {pointer["source_doc_id"] for pointer in run["provenance"]["evidence"].values()} == {
        expected_id
    }


@pytest.mark.parametrize("reverse", [False, True], ids=["primary-first", "workbook-first"])
@pytest.mark.parametrize("explicit_id", [False, True], ids=["generated-id", "submitted-id"])
def test_ingest_secondary_boundary_uses_submitted_workbook_bytes_and_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reverse: bool, explicit_id: bool
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
            if explicit_id:
                entry["document_id"] = "external-track-record-417"
    workbook_path = bundle_path.parent / workbook_name
    _write_performance_workbook(workbook_path, [("2024-01-31", 0.12), ("2024-02-29", -0.07)])
    submitted_bytes = workbook_path.read_bytes()
    if reverse:
        payload["files"].reverse()
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    workbook_index = next(
        index for index, entry in enumerate(payload["files"]) if entry["file_name"] == workbook_name
    )
    expected_id = payload["files"][workbook_index].get(
        "document_id", f"{payload['package_id']}:doc:{workbook_index}"
    )
    observed: list[tuple[str, bytes]] = []
    original = v1_smoke._run_secondary_extraction_boundary_smoke

    def recording_secondary(**kwargs):
        observed.append((kwargs["source_doc_id"], kwargs["content"]))
        return original(**kwargs)

    monkeypatch.setattr(v1_smoke, "_run_secondary_extraction_boundary_smoke", recording_secondary)
    assert main([str(bundle_path), "--out", str(tmp_path / "out")]) == 0
    assert observed == [(expected_id, submitted_bytes)]


@pytest.mark.parametrize("change", ["replace", "remove"])
@pytest.mark.parametrize("extension", [".pdf", ".xlsx"], ids=["primary", "workbook"])
def test_ingest_uses_registered_bytes_after_source_files_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str, extension: str
) -> None:
    """B04/B06: extraction and performance consume the registered document snapshot."""
    from inv_man_intake import v1_smoke

    bundle_path = _write_score_bundle(tmp_path, name="bundle")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    submitted_path = next(
        bundle_path.parent / entry["file_name"]
        for entry in payload["files"]
        if Path(entry["file_name"]).suffix == extension
    )
    original_registration = v1_smoke.register_intake_bundle_file

    def register_then_change_sources(*args, **kwargs):
        registration = original_registration(*args, **kwargs)
        assert registration.accepted
        if change == "remove":
            submitted_path.unlink()
        elif extension == ".xlsx":
            _write_performance_workbook(
                submitted_path, [(as_of, value / 10) for as_of, value in _SCORE_ROWS]
            )
        else:
            submitted_path.write_bytes(submitted_path.read_bytes().replace(b"credit", b"quant"))
        return registration

    monkeypatch.setattr(v1_smoke, "register_intake_bundle_file", register_then_change_sources)
    run = _run_score(bundle_path, tmp_path / "out")

    fields = {field["key"]: field["value"] for field in run["fields"]}
    assert fields["strategy.asset_class"] == "credit"
    assert run["performance"]["monthly"] == [
        {"as_of": as_of, "value": value} for as_of, value in _SCORE_ROWS
    ]
    assert isinstance(run["final_score"], float)


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_ingest_multiple_workbooks_selects_track_record_by_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, order: tuple[int, ...]
) -> None:
    """B05/B16: three-document bundles select the declared workbook in every order."""
    from inv_man_intake import v1_smoke

    bundle_path = _write_score_bundle(tmp_path, name="bundle")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    payload["package_id"] = "pkg_multiple_workbooks"
    # Sort before the declared track record, with different but valid returns.
    decoy_name = "aaa-supporting-returns.xlsx"
    _write_performance_workbook(
        bundle_path.parent / decoy_name,
        [(as_of, value / 10) for as_of, value in _SCORE_ROWS],
    )
    payload["files"].append(
        {
            "file_name": decoy_name,
            "role": "supporting_material",
            "source_ref": "email:supporting-returns",
        }
    )
    payload["files"] = [payload["files"][index] for index in order]
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")
    workbook_index = next(
        index
        for index, entry in enumerate(payload["files"])
        if entry["role"] == "performance_track_record"
    )
    workbook_name = payload["files"][workbook_index]["file_name"]
    workbook_id = f"{payload['package_id']}:doc:{workbook_index}"
    observed: list[tuple[str, bytes]] = []
    original = v1_smoke._run_secondary_extraction_boundary_smoke

    def recording_secondary(**kwargs):
        observed.append((kwargs["source_doc_id"], kwargs["content"]))
        return original(**kwargs)

    monkeypatch.setattr(v1_smoke, "_run_secondary_extraction_boundary_smoke", recording_secondary)
    run = _run_score(bundle_path, tmp_path / "out")

    assert run["inputs"]["file_count"] == 3
    assert observed == [(workbook_id, (bundle_path.parent / workbook_name).read_bytes())]
    assert run["performance"]["monthly"] == [
        {"as_of": as_of, "value": value} for as_of, value in _SCORE_ROWS
    ]
    assert isinstance(run["final_score"], float)
    workbook_pointers = [
        pointer
        for component in run["explainability"]["components"]
        for pointer in component["provenance"]
        if pointer["source_kind"] == "workbook"
    ]
    assert workbook_pointers
    assert {(pointer["source_doc_id"], pointer["reference"]) for pointer in workbook_pointers} == {
        (workbook_id, workbook_name)
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


def test_ingest_rejected_registration_stops_before_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """B03: rejected production intake reports validation errors without smoke assertions."""
    from inv_man_intake import v1_smoke
    from inv_man_intake.run import run_pipeline

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    del payload["metadata"]["fund_name"]
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")

    def forbidden_continuation(**kwargs):
        pytest.fail("rejected production registration must stop before smoke checks or extraction")

    monkeypatch.setattr(v1_smoke, "_assert_registered_package_state", forbidden_continuation)
    monkeypatch.setattr(v1_smoke, "_select_extraction_documents", forbidden_continuation)
    output_dir = tmp_path / "out"
    error = "intake bundle registration rejected: missing_required_metadata"
    with pytest.raises(ValueError, match=f"^{error}$"):
        run_pipeline(bundle_path, output_dir=output_dir)

    assert main([str(bundle_path), "--out", str(output_dir)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"error: intake run failed: {error}\n"
    assert not output_dir.exists(), "rejected intake must not emit successful run artifacts"


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
    _assert_production_performance_source(run)
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


@pytest.mark.parametrize("sufficient_evidence", [False, True], ids=["unavailable", "scored"])
def test_ingest_score_never_calls_smoke_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sufficient_evidence: bool
) -> None:
    """B09: neither production scoring outcome may use fixed smoke components."""
    from inv_man_intake import v1_smoke

    def forbidden_smoke_components(benchmark_correlation):
        pytest.fail("production scoring must never call smoke score components")

    monkeypatch.setattr(v1_smoke, "_score_components", forbidden_smoke_components)
    bundle = (
        _write_score_bundle(tmp_path, name="bundle")
        if sufficient_evidence
        else _write_external_layout_bundle(tmp_path / "bundle")
    )
    run = _run_score(bundle, tmp_path / "out")

    if sufficient_evidence:
        assert isinstance(run["final_score"], float)
        assert run["explainability"]["overall_score"] == pytest.approx(run["final_score"])
    else:
        assert run["final_score"] is None
        assert run["explainability"]["status"] == "unavailable"


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
    # Mean Doc-Lineage confidence of the five key fields; the smoke constant is 0.74.
    assert scores["transparency"] == pytest.approx(0.82)
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
    if not accepted:
        # A real caller-supplied policy rejects Doc-Lineage's 0.82 fields; defaults accept them.
        args += ["--threshold-config", str(_write_review_policy(tmp_path))]
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
    policy_args = ["--threshold-config", str(_write_review_policy(tmp_path))]
    args = [str(bundle), "--out", str(output), *policy_args]
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
    assert main([str(bundle), "--out", str(tmp_path / "new-output"), *policy_args]) == 0
    assert load_validation_queue(queue_file) == (reviewed,)


_CONFLICT_MONTHS = [date(2023 + (index // 12), index % 12 + 1, 15) for index in range(20)]
_CONFLICT_WORKBOOK_DATES = [
    month.replace(day=monthrange(month.year, month.month)[1]).isoformat()
    for month in _CONFLICT_MONTHS
]
_CONFLICT_WORKBOOK_VALUES = [round(0.004 + 0.001 * index, 6) for index in range(20)]


def _monthly_return_lines(conflicts: int) -> list[str]:
    values = list(_CONFLICT_WORKBOOK_VALUES)
    for index in range(conflicts):
        values[index * 7] = round(values[index * 7] + 0.02, 6)
    return [
        f"MONTHLY_RETURN as_of={as_of} value={value} frequency=monthly"
        for as_of, value in zip(_CONFLICT_MONTHS, values, strict=True)
    ]


def _write_pptx_with_slide_lines(
    source: Path,
    target: Path,
    lines: list[str],
    *,
    layout: str,
) -> None:
    import zipfile
    from xml.sax.saxutils import escape

    def _paragraph_xml(line: str) -> str:
        run = f"<a:r><a:t>{escape(line)}</a:t></a:r>"
        if layout == "split_runs":
            midpoint = len(line) // 2
            run = (
                f"<a:r><a:t>{escape(line[:midpoint])}</a:t></a:r>"
                f"<a:r><a:t>{escape(line[midpoint:])}</a:t></a:r>"
            )
        elif layout == "trailing_field":
            run += "<a:fld><a:t> draft</a:t></a:fld>"
        return f"<a:p>{run}</a:p>"

    paragraphs = "".join(_paragraph_xml(line) for line in lines)
    slide = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        "<p:cSld><p:spTree><p:sp><p:txBody><a:bodyPr/>"
        f"{paragraphs}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
    )
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as updated:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == "ppt/presentation.xml":
                data = data.replace(
                    b"</p:sldIdLst>", b'<p:sldId id="258" r:id="rId3"/></p:sldIdLst>'
                )
            elif info.filename == "ppt/_rels/presentation.xml.rels":
                data = data.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/'
                    b'officeDocument/2006/relationships/slide" Target="slides/slide3.xml"/>'
                    b"</Relationships>",
                )
            updated.writestr(info, data)
        updated.writestr("ppt/slides/slide3.xml", slide)


@pytest.mark.parametrize(
    (
        "lines",
        "expected_status",
        "expected_reason",
        "expected_conflicts",
        "expected_overlap",
        "expected_unmatched",
        "layout",
    ),
    [
        (_monthly_return_lines(2), "comparable", None, 2, 20, [], "run"),
        (_monthly_return_lines(2), "comparable", None, 2, 20, [], "split_runs"),
        (_monthly_return_lines(1), "comparable", None, 1, 20, [], "run"),
        (
            _monthly_return_lines(1)[:10]
            + ["MONTHLY_RETURN as_of=2024-09-15 value=0.03 frequency=monthly"],
            "comparable",
            None,
            1,
            10,
            ["2024-09"],
            "run",
        ),
        (None, "unavailable", "unsupported_document_format", None, 0, [], "run"),
        ([], "unavailable", "no_document_monthly_rows", None, 0, [], "run"),
        (
            _monthly_return_lines(0)[:19]
            + [f"MONTHLY_RETURN as_of={_CONFLICT_MONTHS[19]} value=2%"],
            "unavailable",
            "unsupported_document_rows",
            None,
            0,
            [],
            "run",
        ),
        (
            _monthly_return_lines(0)[:1],
            "unavailable",
            "unsupported_document_rows",
            None,
            0,
            [],
            "trailing_field",
        ),
        (
            _monthly_return_lines(0)
            + ["MONTHLY_RETURN as_of=2023-01-05 value=0.5 frequency=monthly"],
            "non_comparable",
            "ambiguous_document_rows",
            None,
            0,
            [],
            "run",
        ),
        (
            ["MONTHLY_RETURN as_of=2019-01-31 value=0.01 frequency=monthly"],
            "non_comparable",
            "no_overlapping_periods",
            None,
            0,
            ["2019-01"],
            "run",
        ),
    ],
    ids=[
        "2-of-20-escalates",
        "2-of-20-escalates-split-runs",
        "1-of-20-at-threshold",
        "1-of-10-partial-overlap-escalates",
        "pdf-primary-unavailable",
        "no-rows-unavailable",
        "malformed-row-unavailable",
        "trailing-field-unavailable",
        "ambiguous-month-non-comparable",
        "nonoverlapping-non-comparable",
    ],
)
def test_production_conflict_over_5pct_emits_performance_conflict_queue_item(
    tmp_path: Path,
    lines: list[str] | None,
    expected_status: str,
    expected_reason: str | None,
    expected_conflicts: int | None,
    expected_overlap: int,
    expected_unmatched: list[str],
    layout: str,
) -> None:
    """#1084: submitted deck returns reach the resolver and >5% conflicts reach the queue."""
    from inv_man_intake.workflow_validation import load_validation_queue

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle_path.read_text())
    primary_entry = next(
        entry for entry in payload["files"] if entry["role"] != "performance_track_record"
    )
    if lines is not None:
        (bundle_path.parent / primary_entry["file_name"]).unlink()
        primary_entry["file_name"] = "submitted-deck.pptx"
        _write_pptx_with_slide_lines(
            _FIXTURE_EXTRACTION / "harborline_strategy_review.pptx",
            bundle_path.parent / primary_entry["file_name"],
            lines,
            layout=layout,
        )
    bundle_path.write_text(json.dumps(payload))
    workbook_name = "summit_arc_track_record.xlsx"
    _write_performance_workbook(
        bundle_path.parent / workbook_name,
        list(zip(_CONFLICT_WORKBOOK_DATES, _CONFLICT_WORKBOOK_VALUES, strict=True)),
    )

    output = tmp_path / "out"
    assert main([str(bundle_path), "--out", str(output)]) == 0
    run = json.loads((output / "run.json").read_text())
    performance = run["performance"]
    comparison = performance["comparison"]
    queue = {
        item.escalation_reason: item
        for item in load_validation_queue(output / "validation-queue.json")
    }

    # Workbook precedence: the resolved series is the workbook's, whatever the deck says.
    assert [point["value"] for point in performance["monthly"]] == _CONFLICT_WORKBOOK_VALUES
    assert [point["as_of"] for point in performance["monthly"]] == _CONFLICT_WORKBOOK_DATES
    assert comparison["status"] == expected_status
    assert comparison["reason"] == expected_reason
    assert comparison["overlap_count"] == expected_overlap
    assert comparison["unmatched_document_periods"] == expected_unmatched
    assert comparison["threshold_percent"] == 5.0
    assert comparison["workbook_source"]["file_name"] == workbook_name
    assert comparison["document_source"]["file_name"] == primary_entry["file_name"]
    primary_id = comparison["document_source"]["document_id"]
    assert primary_id in run["inputs"]["document_ids"]

    if expected_conflicts is None:
        assert performance["comparison_available"] is False
        assert comparison["overlap_count"] == comparison["conflict_count"] == 0
        assert comparison["escalate"] is False and comparison["audit"] == []
        assert "performance_conflict" not in queue
        return

    assert performance["comparison_available"] is True
    assert comparison["conflict_count"] == expected_conflicts
    expected_percentage = 100 * expected_conflicts / expected_overlap
    assert comparison["conflict_percentage"] == pytest.approx(expected_percentage)
    assert comparison["escalate"] is (expected_percentage > 5.0)
    assert len(comparison["audit"]) == expected_overlap
    conflicts = [row for row in comparison["audit"] if row["is_conflict"]]
    assert len(conflicts) == expected_conflicts
    for index, row in enumerate(comparison["audit"]):
        evidence = row["document_evidence"]
        assert row["workbook_as_of"] == _CONFLICT_WORKBOOK_DATES[index]
        assert evidence["document_as_of"] == _CONFLICT_MONTHS[index].isoformat()
        assert evidence["source_doc_id"] == primary_id
        assert evidence["source_page"] == 3
        assert evidence["snippet"].startswith(f"MONTHLY_RETURN as_of={evidence['document_as_of']}")
    if comparison["escalate"]:
        item = queue["performance_conflict"]
        assert item.state == "pending_triage" and item.owner_id is None
        assert item.details == comparison
    else:
        assert "performance_conflict" not in queue


def _break_member_crc(path: Path, member: str) -> None:
    """Store ``member`` uncompressed, then flip one data byte so only its CRC-32 check fails."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(path) as original, zipfile.ZipFile(buffer, "w") as updated:
        for info in original.infolist():
            data = original.read(info.filename)
            if info.filename == member:
                info.compress_type = zipfile.ZIP_STORED
            updated.writestr(info, data)
    content = bytearray(buffer.getvalue())
    with zipfile.ZipFile(io.BytesIO(bytes(content))) as archive:
        header = archive.getinfo(member).header_offset
    name_length = int.from_bytes(content[header + 26 : header + 28], "little")
    extra_length = int.from_bytes(content[header + 28 : header + 30], "little")
    content[header + 30 + name_length + extra_length] ^= 0x01
    path.write_bytes(bytes(content))


def test_production_bad_crc_presentation_part_leaves_comparison_unavailable(
    tmp_path: Path,
) -> None:
    """#1091: an unreadable deck manifest makes the optional comparison unavailable, not fatal."""
    import zipfile

    from inv_man_intake.workflow_validation import load_validation_queue

    bundle_path = _write_external_layout_bundle(tmp_path / "bundle")
    payload = json.loads(bundle_path.read_text())
    primary_entry = next(
        entry for entry in payload["files"] if entry["role"] != "performance_track_record"
    )
    (bundle_path.parent / primary_entry["file_name"]).unlink()
    primary_entry["file_name"] = "submitted-deck.pptx"
    deck_path = bundle_path.parent / primary_entry["file_name"]
    # 2-of-20 conflicting rows would escalate if the comparison could read the deck.
    _write_pptx_with_slide_lines(
        _FIXTURE_EXTRACTION / "harborline_strategy_review.pptx",
        deck_path,
        _monthly_return_lines(2),
        layout="run",
    )
    _break_member_crc(deck_path, "ppt/presentation.xml")
    bundle_path.write_text(json.dumps(payload))
    workbook_name = "summit_arc_track_record.xlsx"
    _write_performance_workbook(
        bundle_path.parent / workbook_name,
        list(zip(_CONFLICT_WORKBOOK_DATES, _CONFLICT_WORKBOOK_VALUES, strict=True)),
    )
    with zipfile.ZipFile(deck_path) as archive:
        with pytest.raises(zipfile.BadZipFile, match="Bad CRC-32"):
            archive.read("ppt/presentation.xml")
        assert all(
            archive.read(name) for name in archive.namelist() if name.startswith("ppt/slides/slide")
        )

    output = tmp_path / "out"
    assert main([str(bundle_path), "--out", str(output)]) == 0

    run = json.loads((output / "run.json").read_text())
    fields = {field["key"]: field for field in run["fields"]}
    assert fields["strategy.asset_class"]["value"] == "credit"
    performance = run["performance"]
    assert [point["value"] for point in performance["monthly"]] == _CONFLICT_WORKBOOK_VALUES
    assert [point["as_of"] for point in performance["monthly"]] == _CONFLICT_WORKBOOK_DATES
    comparison = performance["comparison"]
    assert performance["comparison_available"] is False
    assert comparison["status"] == "unavailable"
    assert comparison["reason"] == "unsupported_document_format"
    assert comparison["workbook_source"]["file_name"] == workbook_name
    assert comparison["document_source"]["file_name"] == primary_entry["file_name"]
    assert comparison["overlap_count"] == comparison["conflict_count"] == 0
    assert comparison["escalate"] is False and comparison["audit"] == []
    queue = load_validation_queue(output / "validation-queue.json")
    assert "performance_conflict" not in {item.escalation_reason for item in queue}
