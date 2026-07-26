"""Tests for the browser-agnostic one-page strategy summary model."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from inv_man_intake.export.one_pager import build_one_pager
from inv_man_intake.extraction.providers.base import ExtractedDocumentResult, ExtractedField
from inv_man_intake.intake.standard_elements import load_standard_element_library
from inv_man_intake.packet import PacketFile, ingest_packet

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "intake" / "pdf_primary_mixed_bundle.json"


class _FixtureProvider:
    @property
    def name(self) -> str:
        return "fixture"

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        _ = content
        fields = (
            ExtractedField(
                "identity.manager", "Summit Arc Advisors", 0.9, source_doc_id, 1, "fixture"
            ),
            ExtractedField("performance.net_return_1y", "12.5%", 0.8, source_doc_id, 1, "fixture"),
        )
        return ExtractedDocumentResult(source_doc_id, self.name, fields)


def _profile():
    library = load_standard_element_library(
        {
            "version": "one-pager-test",
            "non_authoritative": True,
            "doc_types": {
                "deck": [
                    {"key": "identity.manager", "detector_name": "field_present", "mandatory": True}
                ]
            },
        }
    )
    return ingest_packet(
        (PacketFile("fixture", FIXTURE.read_bytes(), "fixture_deck.json"),),
        provider=_FixtureProvider(),
        standard_library=library,
        packet_id="one-pager-fixture",
    )


def test_summary_contains_required_sections_from_a_real_packet() -> None:
    """The committed packet fixture produces every required, non-placeholder section."""

    model = build_one_pager(_profile())
    assert ("Manager", "Summit Arc Advisors") in {
        (field.label, field.value) for field in model.identity
    }
    assert {field.label for field in model.coverage} == {
        "Documents",
        "Document types",
        "Standard elements",
    }
    assert {field.label for field in model.return_stats} == {"Performance / Net Return 1Y"}
    assert model.provenance_citations == (
        "fixture:identity.manager:p1:fixture",
        "fixture:performance.net_return_1y:p1:fixture",
    )
    assert model.final_score == _profile().scores["extraction_confidence"]
    assert "Summit Arc" in model.title
    assert Counter(field.label for field in model.explainability)["Extraction Confidence"] == 1
    rendered = str(model.as_dict()).lower()
    assert not any(marker in rendered for marker in ("lorem", "placeholder", "tbd", "todo"))


def test_removing_explainability_breaks_the_required_section() -> None:
    """Deliberate-break guard: score components must not disappear from the model."""

    model = build_one_pager(_profile())
    assert model.explainability


@pytest.mark.parametrize("score", [math.nan, math.inf, None])
def test_summary_rejects_non_finite_or_missing_scores(score: object) -> None:
    with pytest.raises(ValueError, match="finite"):
        build_one_pager(replace(_profile(), scores={"final_score": score}))


def test_summary_bounds_dense_profile_content() -> None:
    model = build_one_pager(
        replace(
            _profile(),
            identity={
                "identity.manager": "M" * 200,
                **{f"identity.field_{i}": "V" * 200 for i in range(8)},
            },
            scores={f"score_{i}": 0.5 for i in range(8)},
            returns_metrics={f"return_{i}": "R" * 200 for i in range(8)},
        )
    )
    assert (
        len(model.identity) == 4 and len(model.explainability) == 5 and len(model.return_stats) == 4
    )
    assert model.identity[0].label == "Manager"
    assert all(
        len(field.value) <= 80
        for section in (model.identity, model.return_stats)
        for field in section
    )
