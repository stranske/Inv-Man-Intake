"""Deterministic document-type classification for extraction threshold routing."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class DocumentType(StrEnum):
    """Known screening document types used to select expected-field profiles."""

    PITCHBOOK = "pitchbook"
    TEAR_SHEET = "tear_sheet"
    MONTHLY_LETTER = "monthly_letter"
    DDQ = "ddq"
    UNKNOWN = "unknown"


_DOCUMENT_TYPE_KEYWORDS: tuple[tuple[DocumentType, tuple[str, ...]], ...] = (
    (
        DocumentType.DDQ,
        ("ddq", "due diligence questionnaire", "questionnaire"),
    ),
    (
        DocumentType.MONTHLY_LETTER,
        ("monthly letter", "investor letter", "monthly commentary", "month-end"),
    ),
    (
        DocumentType.TEAR_SHEET,
        ("tear sheet", "tearsheet", "factsheet", "fact sheet", "one pager"),
    ),
    (
        DocumentType.PITCHBOOK,
        ("pitchbook", "pitch book", "private placement memorandum", "ppm"),
    ),
)


def classify_doc_type(content: str | bytes | Iterable[str]) -> DocumentType:
    """Classify a document from deterministic text cues, falling back to unknown."""

    text = _normalize_content(content)
    if not text:
        return DocumentType.UNKNOWN

    for document_type, keywords in _DOCUMENT_TYPE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return document_type

    return DocumentType.UNKNOWN


def _normalize_content(content: str | bytes | Iterable[str]) -> str:
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore").casefold()
    if isinstance(content, str):
        return content.casefold()
    return "\n".join(content).casefold()
