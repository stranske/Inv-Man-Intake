"""Data-only consultant-review ontology must surface without code changes."""

from __future__ import annotations

from pathlib import Path

from inv_man_intake.intake.standard_elements import load_standard_element_library

STUB_PATH = Path(__file__).resolve().parents[2] / "config" / "standard_elements" / "_stub.json"


def test_sections_resolve_without_code_change() -> None:
    library = load_standard_element_library(STUB_PATH)

    assert "report.consultant_review" in library.doc_types()

    elements = library.elements_for("report.consultant_review")
    assert len(elements) >= 15

    keys = [element.key for element in elements]
    assert all(key.startswith("consultant.") for key in keys)
    assert len(keys) == len(set(keys))
    assert all(element.mandatory is False for element in elements)
    assert library.non_authoritative is True
