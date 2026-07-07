"""Conformance gates for the standard-element-library port."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inv_man_intake.intake.standard_elements import (
    DataDrivenStandardElementLibrary,
    StandardElement,
    classify_element_standardness,
    load_standard_element_library,
)

STUB_PATH = Path("config/standard_elements/_stub.json")
SRC_ROOT = Path("src/inv_man_intake")


def test_conformance_against_stub() -> None:
    library = load_standard_element_library(STUB_PATH)

    assert library.non_authoritative is True
    assert library.doc_types() == ("stub_pitchbook", "stub_tear_sheet")

    elements = library.elements_for("stub_pitchbook")
    assert [element.key for element in elements] == [
        "operations.aum",
        "terms.management_fee",
    ]

    coverage = library.evaluate_coverage(
        "stub_pitchbook",
        {
            "field_key": "operations.aum",
            "fields": {"operations.aum"},
            "value": 42.0,
        },
    )

    assert [(item.key, item.detected, item.standardness) for item in coverage] == [
        ("operations.aum", True, "unknown"),
        ("terms.management_fee", False, "unknown"),
    ]


def test_data_only_doc_type_addition_surfaces_without_app_code_change(tmp_path: Path) -> None:
    payload = json.loads(STUB_PATH.read_text(encoding="utf-8"))
    payload["doc_types"]["capital_call_notice"] = [
        {
            "key": "operations.capital_call_due_date",
            "detector_name": "field_present",
            "mandatory": True,
        }
    ]
    custom_stub = tmp_path / "standard-elements.json"
    custom_stub.write_text(json.dumps(payload), encoding="utf-8")

    library = load_standard_element_library(custom_stub)

    assert "capital_call_notice" in library.doc_types()
    assert library.elements_for("capital_call_notice")[0].key == (
        "operations.capital_call_due_date"
    )

    source_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in SRC_ROOT.rglob("*.py")
        if path.name != "standard_elements.py"
    )
    assert "capital_call_notice" not in source_text
    assert "operations.capital_call_due_date" not in source_text


def test_judgment_hook_is_unknown_only() -> None:
    library = load_standard_element_library(STUB_PATH)
    element = library.elements_for("stub_tear_sheet")[0]

    assert classify_element_standardness(element=element, extracted={}) == "unknown"


def test_schema_boolean_fields_fail_closed() -> None:
    payload = json.loads(STUB_PATH.read_text(encoding="utf-8"))

    payload["non_authoritative"] = "yes"
    with pytest.raises(ValueError, match="non_authoritative"):
        load_standard_element_library(payload)

    payload = json.loads(STUB_PATH.read_text(encoding="utf-8"))
    payload["doc_types"]["stub_pitchbook"][0]["mandatory"] = "false"
    with pytest.raises(ValueError, match="mandatory"):
        load_standard_element_library(payload)


def test_duplicate_element_keys_are_rejected() -> None:
    payload = json.loads(STUB_PATH.read_text(encoding="utf-8"))
    payload["doc_types"]["stub_pitchbook"].append(
        {
            "key": "operations.aum",
            "detector_name": "field_present",
            "mandatory": False,
        }
    )

    with pytest.raises(ValueError, match="duplicate element key") as excinfo:
        load_standard_element_library(payload)
    assert "operations.aum" in str(excinfo.value)


def test_doc_types_are_deterministic_and_empty_detector_registry_is_honored() -> None:
    payload = json.loads(STUB_PATH.read_text(encoding="utf-8"))
    payload["doc_types"] = {
        "zeta_doc": payload["doc_types"]["stub_pitchbook"],
        "alpha_doc": payload["doc_types"]["stub_tear_sheet"],
    }

    library = load_standard_element_library(payload)
    assert library.doc_types() == ("alpha_doc", "zeta_doc")

    with pytest.raises(ValueError, match="unknown detector reference"):
        DataDrivenStandardElementLibrary(
            version="test",
            non_authoritative=True,
            elements_by_doc_type={
                "sample": (
                    StandardElement(
                        key="field.alpha",
                        detector_name="field_present",
                        mandatory=True,
                    ),
                )
            },
            detectors={},
        )
