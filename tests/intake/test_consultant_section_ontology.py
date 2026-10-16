"""Data-only consultant-review ontology must surface without code changes."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.intake.standard_elements import load_standard_element_library

STUB_PATH = Path(__file__).resolve().parents[2] / "config" / "standard_elements" / "_stub.json"

EXPECTED_KEYS = frozenset(
    {
        "consultant.executive_summary",
        "consultant.manager_overview",
        "consultant.investment_strategy",
        "consultant.performance",
        "consultant.attribution",
        "consultant.benchmark_analysis",
        "consultant.risk",
        "consultant.portfolio",
        "consultant.holdings_analysis",
        "consultant.fees",
        "consultant.organization",
        "consultant.team_and_personnel",
        "consultant.esg",
        "consultant.operations",
        "consultant.compliance",
        "consultant.due_diligence",
        "consultant.outlook",
        "consultant.recommendation",
    }
)


def test_sections_resolve_without_code_change() -> None:
    library = load_standard_element_library(STUB_PATH)

    assert "report.consultant_review" in library.doc_types()

    elements = library.elements_for("report.consultant_review")
    keys = [element.key for element in elements]
    assert len(keys) == len(set(keys))
    # Exact set, so removing or renaming ONE key fails (the issue's deliberate-break gate). Adding a
    # section is still a data-only change; it just means extending this expected set on purpose.
    assert set(keys) == EXPECTED_KEYS
    assert len(keys) >= 15
    assert all(key.startswith("consultant.") for key in keys)
    assert all(element.detector_name == "field_present" for element in elements)
    assert all(element.mandatory is False for element in elements)
    assert library.non_authoritative is True
