"""Doc-Lineage adapter contract, including page provenance and unreadable pages."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pytest

from inv_man_intake.extraction.providers.doc_lineage_adapter import (
    DocLineageExtractionProvider,
    IncompleteExtractionError,
)


@dataclass(frozen=True)
class _Span:
    text: str
    page: int | None
    bbox: tuple[float, float, float, float] | None = None
    source: str = "text_layer"


@dataclass(frozen=True)
class _Coverage:
    pages_with_text_layer: int
    pages_recognized: int
    pages_unreadable: int


@dataclass(frozen=True)
class _Document:
    spans: list[_Span]
    coverage: _Coverage


def _synthetic_pdf() -> bytes:
    from reportlab.pdfgen import canvas

    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(72, 720, "Strategy asset class: Equity page 99")
    pdf.showPage()
    pdf.drawString(72, 720, "AUM: $42M")
    pdf.save()
    return stream.getvalue()


def _mixed_pdf() -> bytes:
    from reportlab.pdfgen import canvas

    stream = BytesIO()
    pdf = canvas.Canvas(stream)
    pdf.drawString(72, 720, "Strategy asset class: Equity")
    pdf.showPage()
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


def test_adapter_emits_page_pointers(monkeypatch: pytest.MonkeyPatch) -> None:
    upstream = pytest.importorskip("doc_lineage.extract")
    monkeypatch.setattr(upstream, "default_ocr_backend", lambda: None)
    provider = DocLineageExtractionProvider()

    result = provider.extract("intake-123", _synthetic_pdf())

    assert result.source_doc_id == "intake-123"
    fields = {field.key: field for field in result.fields}
    assert fields["strategy.asset_class"].source_page == 1
    assert fields["strategy.asset_class"].location.source_page == 1
    assert fields["operations.aum"].source_page == 2
    assert fields["operations.aum"].location.source_page == 2
    assert all(field.method == "doc-lineage:text_layer" for field in fields.values())


def test_adapter_rejects_missing_page_pointer() -> None:
    document = _Document(
        spans=[_Span("AUM: $42M", None)],
        coverage=_Coverage(1, 0, 0),
    )
    provider = DocLineageExtractionProvider(
        extractor=lambda *_args, **_kwargs: document,
        cache_factory=lambda: object(),
    )

    with pytest.raises(ValueError, match="invalid PDF page pointer"):
        provider.extract("doc-null-page", b"%PDF-test")


def test_adapter_uses_upstream_ocr_for_one_scanned_page() -> None:
    upstream = pytest.importorskip("doc_lineage.extract")
    pytest.importorskip("pypdfium2")

    class Recognizer:
        def recognize(self, _image: object, *, rotation: int) -> str:
            assert rotation == 0
            return "AUM: $42M"

    def extract(path: Path, **kwargs: object) -> object:
        return upstream.extract(path, ocr_backend=Recognizer(), **kwargs)

    provider = DocLineageExtractionProvider(
        extractor=extract,
        cache_factory=upstream.ExtractCache,
    )

    result = provider.extract("mixed-pdf", _mixed_pdf())

    fields = {field.key: field for field in result.fields}
    assert fields["strategy.asset_class"].source_page == 1
    assert fields["strategy.asset_class"].method == "doc-lineage:text_layer"
    assert fields["operations.aum"].source_page == 2
    assert fields["operations.aum"].method == "doc-lineage:ocr"


def test_adapter_maps_collapsed_labels_without_cross_page_values() -> None:
    document = _Document(
        spans=[
            _Span("Strategy asset class: Equity Management fee: 2%", 1, (1, 2, 3, 4)),
            _Span("AUM: $42M", 2, source="ocr"),
        ],
        coverage=_Coverage(1, 1, 0),
    )
    provider = DocLineageExtractionProvider(
        extractor=lambda *_args, **_kwargs: document,
        cache_factory=lambda: object(),
    )

    result = provider.extract("doc-1", b"%PDF-test")

    fields = {field.key: field for field in result.fields}
    assert fields["strategy.asset_class"].value == "Equity"
    assert fields["terms.management_fee"].value == "2%"
    assert fields["strategy.asset_class"].location.bbox == (1, 2, 3, 4)
    assert fields["operations.aum"].source_page == 2
    assert fields["operations.aum"].method == "doc-lineage:ocr"


def test_adapter_reports_unreadable_pages_and_cleans_temporary_pdf() -> None:
    paths: list[Path] = []

    def extract(path: Path, **kwargs: object) -> _Document:
        assert path.suffix == ".pdf"
        assert path.read_bytes() == b"sensitive PDF bytes"
        assert kwargs["ocr_enabled"] is True
        paths.append(path)
        return _Document(
            spans=[_Span("AUM: $42M", 1)],
            coverage=_Coverage(1, 0, 1),
        )

    provider = DocLineageExtractionProvider(extractor=extract, cache_factory=lambda: object())

    with pytest.raises(IncompleteExtractionError) as caught:
        provider.extract("doc-2", b"sensitive PDF bytes")

    assert caught.value.coverage.pages_unreadable == 1
    assert caught.value.partial_result.fields[0].source_page == 1
    assert paths and not paths[0].exists()


def test_adapter_cleans_temporary_pdf_after_upstream_failure() -> None:
    paths: list[Path] = []

    def extract(path: Path, **_kwargs: object) -> _Document:
        paths.append(path)
        raise ValueError("invalid PDF")

    provider = DocLineageExtractionProvider(extractor=extract, cache_factory=lambda: object())

    with pytest.raises(ValueError, match="invalid PDF"):
        provider.extract("doc-3", b"invalid")

    assert paths and not paths[0].exists()
