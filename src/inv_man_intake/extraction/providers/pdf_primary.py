"""Dependency-free PDF bytes provider for deterministic v1 smoke fixtures."""

from __future__ import annotations

import re

from inv_man_intake.extraction.providers.base import (
    ExtractedDocumentResult,
    ExtractedField,
    SourceLocation,
    validate_extracted_document_result,
)


class UnsupportedDocumentFormatError(ValueError):
    """Raised when a provider receives bytes outside its narrow format support."""


class PdfPrimaryExtractionProvider:
    """Extract canonical v1 fields from small text-bearing PDF bytes.

    This is intentionally narrow: it validates PDF framing and reads literal text
    operands from content streams. It is suitable for committed smoke fixtures,
    not production OCR or layout reconstruction.
    """

    _PATTERNS: tuple[tuple[str, str, float], ...] = (
        ("strategy.asset_class", r"strategy asset class\s*[:\-]\s*([^;\n]+)", 0.93),
        ("terms.management_fee", r"management fee\s*[:\-]\s*([0-9]+(?:\.[0-9]+)?%)", 0.91),
        ("performance.net_return_1y", r"net return 1y\s*[:\-]\s*([0-9.-]+%)", 0.88),
        ("operations.aum", r"aum\s*[:\-]\s*([$A-Za-z0-9.]+)", 0.72),
        ("team.key_person_risk", r"key person risk\s*[:\-]\s*([^;\n]+)", 0.50),
    )
    _PAGE_PATTERN = re.compile(r"\bpage\s+(?P<page>[0-9]+)\b", re.IGNORECASE)
    _TEXT_LITERAL_PATTERN = re.compile(rb"\((?:\\.|[^\\()])*\)")
    _STREAM_PATTERN = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)

    @property
    def name(self) -> str:
        return "pdf-primary"

    def extract(self, source_doc_id: str, content: bytes) -> ExtractedDocumentResult:
        if not self._is_supported_pdf(content):
            raise UnsupportedDocumentFormatError("pdf-primary only supports PDF bytes")

        text = self._extract_literal_text(content)
        fields: list[ExtractedField] = []
        for key, pattern, confidence in self._PATTERNS:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            fields.append(
                ExtractedField(
                    key=key,
                    value=match.group(1).strip().rstrip("."),
                    confidence=confidence,
                    source_doc_id=source_doc_id,
                    source_page=self._source_page_for_match(text=text, match_start=match.start()),
                    method=self.name,
                    location=SourceLocation(
                        source_doc_id=source_doc_id,
                        source_page=self._source_page_for_match(
                            text=text,
                            match_start=match.start(),
                        ),
                    ),
                    snippet=match.group(0).strip(),
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
    def _extract_literal_text(cls, content: bytes) -> str:
        chunks = []
        for stream_body in cls._STREAM_PATTERN.findall(content):
            for raw_literal in cls._TEXT_LITERAL_PATTERN.findall(stream_body):
                chunks.append(cls._decode_pdf_literal(raw_literal[1:-1]))
        return "\n".join(chunk for chunk in chunks if chunk.strip())

    @staticmethod
    def _is_supported_pdf(content: bytes) -> bool:
        if not content.startswith(b"%PDF-"):
            return False
        return b"%%EOF" in content

    @staticmethod
    def _decode_pdf_literal(raw: bytes) -> str:
        decoded: list[str] = []
        index = 0
        while index < len(raw):
            current = raw[index]
            if current == 92 and index + 1 < len(raw):
                index += 1
                escaped = raw[index]
                if escaped in (10, 13):
                    if escaped == 13 and index + 1 < len(raw) and raw[index + 1] == 10:
                        index += 1
                    index += 1
                    continue
                if 48 <= escaped <= 55:
                    octal = bytes([escaped])
                    while len(octal) < 3 and index + 1 < len(raw) and 48 <= raw[index + 1] <= 55:
                        index += 1
                        octal += bytes([raw[index]])
                    decoded.append(chr(int(octal, 8)))
                    index += 1
                    continue
                decoded.append(
                    {
                        ord("n"): "\n",
                        ord("r"): "\r",
                        ord("t"): "\t",
                        ord("b"): "\b",
                        ord("f"): "\f",
                        ord("("): "(",
                        ord(")"): ")",
                        ord("\\"): "\\",
                    }.get(escaped, chr(escaped))
                )
            else:
                decoded.append(chr(current))
            index += 1
        return "".join(decoded)

    @classmethod
    def _source_page_for_match(cls, *, text: str, match_start: int) -> int:
        page = 0
        for match in cls._PAGE_PATTERN.finditer(text[:match_start]):
            page = int(match.group("page"))
        return page
