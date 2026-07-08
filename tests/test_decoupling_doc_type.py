from __future__ import annotations

from pathlib import Path

from inv_man_intake.extraction.providers.base import (  # type: ignore[import-untyped]
    ExtractedDocumentResult,
    ExtractedField,
)
from inv_man_intake.intake.standard_elements import (  # type: ignore[import-untyped]
    load_standard_element_library,
)
from inv_man_intake.packet import PacketFile, ingest_packet  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
THROWAWAY_DOC_TYPE = "issue_721_throwaway_side_letter"


class _Provider:
    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        _ = content
        return ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            provider_name="issue-721-stub-provider",
            fields=(
                ExtractedField(
                    key="custom.issue_721_metric",
                    value="present",
                    confidence=0.91,
                    source_doc_id=source_doc_id,
                    source_page=1,
                    method="issue-721-stub",
                ),
            ),
        )


def test_issue_721_throwaway_doc_type_is_fixture_driven_without_app_branching() -> None:
    library = load_standard_element_library(
        {
            "version": "issue-721-decoupling-test",
            "non_authoritative": True,
            "doc_types": {
                THROWAWAY_DOC_TYPE: [
                    {
                        "key": "custom.issue_721_metric",
                        "detector_name": "field_present",
                        "mandatory": True,
                    }
                ]
            },
        }
    )

    profile = ingest_packet(
        (
            PacketFile(
                document_id="issue-721-stub",
                filename="issue-721-side-letter.txt",
                content=f"{THROWAWAY_DOC_TYPE} fixture payload".encode(),
            ),
        ),
        provider=_Provider(),
        standard_library=library,
        packet_id="issue-721-stub",
    )

    coverage = profile.per_doc_standard_element_coverage["issue-721-stub"]
    assert profile.documents[0].document_type == THROWAWAY_DOC_TYPE
    assert coverage[0].key == "custom.issue_721_metric"
    assert coverage[0].detected is True

    application_sources = (
        ROOT / "src" / "inv_man_intake" / "packet.py",
        ROOT / "app" / "streamlit_app.py",
    )
    for source in application_sources:
        text = source.read_text(encoding="utf-8")
        assert THROWAWAY_DOC_TYPE not in text
        assert "custom.issue_721_metric" not in text
