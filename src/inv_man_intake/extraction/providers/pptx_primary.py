"""Dependency-free PPTX bytes provider for deterministic v1 smoke fixtures."""

from __future__ import annotations

import io
import math
import re
import zipfile
from dataclasses import dataclass
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
_MONTHLY_RETURN_PREFIX = "MONTHLY_RETURN"
_MONTHLY_RETURN_PATTERN = re.compile(
    r"^MONTHLY_RETURN as_of=(?P<as_of>[0-9]{4}-[0-9]{2}-[0-9]{2})"
    r" value=(?P<value>[-+]?[0-9]+(?:\.[0-9]+)?) frequency=monthly$"
)


@dataclass(frozen=True)
class MonthlyReturnRow:
    """One canonical ``MONTHLY_RETURN`` slide row with its document evidence."""

    as_of: str
    value: float
    source_doc_id: str
    source_page: int
    snippet: str

    def as_timeseries_row(self) -> dict[str, object]:
        """Return the row shape accepted by ``load_document_timeseries``."""

        return {"frequency": "monthly", "as_of": self.as_of, "value": self.value}


@dataclass(frozen=True)
class MonthlyReturnRows:
    """Canonical monthly-return rows plus ``MONTHLY_RETURN`` lines that did not match."""

    rows: tuple[MonthlyReturnRow, ...]
    unsupported_lines: tuple[str, ...]


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
        ("operations.aum", r"aum\s*[:\-]\s*([^\r\n]+)", 0.82),
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

    def monthly_return_rows(self, source_doc_id: str, content: bytes) -> MonthlyReturnRows:
        """Read explicit ``MONTHLY_RETURN as_of=YYYY-MM-DD value=<decimal> frequency=monthly`` rows.

        Only whole slide text lines in exactly that form are rows. Any other line
        starting with ``MONTHLY_RETURN`` is reported as unsupported rather than
        guessed at; values are decimal returns, never percentages.
        """

        rows: list[MonthlyReturnRow] = []
        unsupported: list[str] = []
        for slide_index, text in self._slide_texts(content):
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line.startswith(_MONTHLY_RETURN_PREFIX):
                    continue
                match = _MONTHLY_RETURN_PATTERN.match(line)
                value = float(match.group("value")) if match else math.nan
                if match is None or not math.isfinite(value):
                    unsupported.append(line)
                    continue
                rows.append(
                    MonthlyReturnRow(
                        as_of=match.group("as_of"),
                        value=value,
                        source_doc_id=source_doc_id,
                        source_page=slide_index,
                        snippet=line,
                    )
                )
        return MonthlyReturnRows(rows=tuple(rows), unsupported_lines=tuple(unsupported))

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
