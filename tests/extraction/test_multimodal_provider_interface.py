"""Tests for the multimodal extraction provider interface contract."""

from __future__ import annotations

from inv_man_intake.extraction.providers.base import (
    ExtractedImage,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedTextBlock,
    MultiModalExtractionProvider,
    ProviderExtractionOutput,
    SourceLocation,
)


class _DummyMultiModalProvider:
    @property
    def name(self) -> str:
        return "dummy-multimodal"

    def extract_modalities(self, source_doc_id: str, content: bytes) -> ProviderExtractionOutput:
        _ = content
        location = SourceLocation(source_doc_id=source_doc_id, source_page=1)
        return ProviderExtractionOutput(
            source_doc_id=source_doc_id,
            provider_name=self.name,
            text_blocks=(ExtractedTextBlock(text="sample text", location=location),),
            tables=(
                ExtractedTable(
                    table_id="table-1",
                    location=location,
                    cells=(ExtractedTableCell(row_index=0, column_index=0, value="A1"),),
                ),
            ),
            images=(ExtractedImage(image_id="img-1", location=location, ocr_text="ocr"),),
        )


def test_multimodal_provider_protocol_runtime_conformance() -> None:
    provider = _DummyMultiModalProvider()
    assert isinstance(provider, MultiModalExtractionProvider)


def test_provider_output_supports_text_table_and_image_modalities() -> None:
    provider = _DummyMultiModalProvider()
    result = provider.extract_modalities(source_doc_id="doc_1", content=b"payload")

    assert isinstance(result, ProviderExtractionOutput)
    assert result.source_doc_id == "doc_1"
    assert result.provider_name == "dummy-multimodal"

    assert len(result.text_blocks) == 1
    assert result.text_blocks[0].text == "sample text"

    assert len(result.tables) == 1
    assert result.tables[0].cells[0].value == "A1"

    assert len(result.images) == 1
    assert result.images[0].ocr_text == "ocr"
