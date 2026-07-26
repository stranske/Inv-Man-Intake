"""Tests for the browser-agnostic one-page strategy summary model."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

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
    assert model.identity and model.coverage and model.explainability
    assert model.provenance_citations and model.return_stats
    assert model.final_score == _profile().scores["extraction_confidence"]
    assert "Summit Arc" in model.title
    assert Counter(field.label for field in model.explainability)["Extraction Confidence"] == 1
    assert "lorem" not in str(model.as_dict()).lower()


def test_removing_explainability_breaks_the_required_section() -> None:
    """Deliberate-break guard: score components must not disappear from the model."""

    model = build_one_pager(_profile())
    assert model.explainability
