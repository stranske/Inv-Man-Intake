"""Dependency-free PPTX bytes provider for deterministic v1 smoke fixtures."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree as ET

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    SnippetMetadata,
    SourceLocation,
    validate_extracted_document_result,
)
from inv_man_intake.extraction.providers.pdf_primary import UnsupportedDocumentFormatError

_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_TEXT_TAG = f"{{{_DRAWINGML_NS}}}t"
_SLIDE_NAME_PATTERN = re.compile(r"^ppt/slides/slide(?P<index>[1-9][0-9]*)\.xml$")


class PptxPrimaryExtractionProvider:
    """Extract canonical v1 fields from small text-bearing PPTX bytes.

    Like the PDF provider this is intentionally narrow: it validates Open
    Packaging Convention framing and reads DrawingML ``<a:t>`` text runs from
    each slide. DrawingML text is explicit structured content rather than
    reconstructed content-stream literals, so matched fields carry higher
    confidence than the PDF provider's stream-parsed equivalents.
    """

    _PATTERNS: tuple[tuple[str, str, float], ...] = (
        ("strategy.asset_class", r"strategy asset class\s*[:\-]\s*([^;\n]+)", 0.95),
        ("terms.management_fee", r"management fee\s*[:\-]\s*([0-9]+(?:\.[0-9]+)?%)", 0.93),
        ("performance.net_return_1y", r"net return 1y\s*[:\-]\s*([0-9.-]+%)", 0.90),
        ("operations.aum", r"aum\s*[:\-]\s*([$A-Za-z0-9.]+)", 0.82),
        ("team.key_person_risk", r"key person risk\s*[:\-]\s*([^;\n]+)", 0.80),
    )

    @property
    def name(self) -> str:
        return "pptx-primary"

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        slide_texts = self._slide_texts(content)

        fields: list[ExtractedField] = []
        seen_keys: set[str] = set()
        for slide_index, text in slide_texts:
            for key, pattern, confidence in self._PATTERNS:
                if key in seen_keys:
                    continue
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if not match:
                    continue
                seen_keys.add(key)
                fields.append(
                    ExtractedField(
                        key=key,
                        value=match.group(1).strip().rstrip("."),
                        confidence=confidence,
                        source_doc_id=source_doc_id,
                        source_page=slide_index,
                        method=self.name,
                        location=SourceLocation(
                            source_doc_id=source_doc_id,
                            source_page=slide_index,
                        ),
                        snippet=match.group(0).strip(),
                        snippet_metadata=SnippetMetadata(
                            kind="regex-match",
                            char_start=match.start(),
                            char_end=match.end(),
                        ),
                    )
                )

        result = ExtractedDocumentResult(
            source_doc_id=source_doc_id,
            fields=tuple(fields),
            provider_name=self.name,
        )
        validate_extracted_document_result(result)
        return result

    @classmethod
    def _slide_texts(cls, content: bytes) -> list[tuple[int, str]]:
        if not content.startswith(b"PK\x03\x04"):
            raise UnsupportedDocumentFormatError("pptx-primary only supports PPTX bytes")
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise UnsupportedDocumentFormatError("pptx-primary only supports PPTX bytes") from exc
        with archive as zf:
            names = zf.namelist()
            if "ppt/presentation.xml" not in names:
                raise UnsupportedDocumentFormatError("pptx-primary only supports PPTX bytes")
            slides: list[tuple[int, str]] = []
            for name in names:
                slide_match = _SLIDE_NAME_PATTERN.match(name)
                if slide_match is None:
                    continue
                slide_index = int(slide_match.group("index"))
                try:
                    root = ET.fromstring(zf.read(name))
                except (ET.ParseError, UnicodeDecodeError) as exc:
                    raise UnsupportedDocumentFormatError(
                        "pptx-primary only supports PPTX bytes"
                    ) from exc
                runs = [node.text or "" for node in root.iter(_TEXT_TAG)]
                slides.append((slide_index, "\n".join(run for run in runs if run.strip())))
        slides.sort(key=lambda item: item[0])
        return slides
