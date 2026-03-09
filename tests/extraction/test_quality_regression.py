"""Regression checks for extraction QA corpus baseline metrics."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.extraction.quality import generate_quality_report

_CORPUS_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "extraction" / "qa_corpus.json"


def test_extraction_quality_report_meets_baseline_metrics() -> None:
    report = generate_quality_report(_CORPUS_PATH)
    summary = report["summary"]

    assert report["fixture_count"] >= 3
    assert summary["accuracy"] >= 0.75
    assert summary["completeness"] >= 0.75
    assert summary["parser_failure_count"] == 0
    assert summary["fallback_usage_count"] == 0


def test_extraction_quality_report_surfaces_fixture_level_gaps() -> None:
    report = generate_quality_report(_CORPUS_PATH)

    fixture_reports = report["fixtures"]
    assert fixture_reports
    assert all("document_id" in fixture for fixture in fixture_reports)
    assert all("matched_count" in fixture for fixture in fixture_reports)
