"""Deterministic document-type classification for extraction threshold routing."""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum

from inv_man_intake.intake.standard_elements import StandardElementLibrary


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
        DocumentType.TEAR_SHEET,
        ("tear sheet", "tearsheet", "factsheet", "fact sheet", "one pager"),
    ),
    (
        DocumentType.MONTHLY_LETTER,
        ("monthly letter", "investor letter", "monthly commentary"),
    ),
    (
        DocumentType.PITCHBOOK,
        ("pitchbook", "pitch book", "private placement memorandum"),
    ),
)

_STANDARD_LIBRARY_TYPE_ALIASES: dict[str, DocumentType] = {
    "pitchbook": DocumentType.PITCHBOOK,
    "pitch_book": DocumentType.PITCHBOOK,
    "tear_sheet": DocumentType.TEAR_SHEET,
    "tearsheet": DocumentType.TEAR_SHEET,
    "factsheet": DocumentType.TEAR_SHEET,
    "fact_sheet": DocumentType.TEAR_SHEET,
    "monthly_letter": DocumentType.MONTHLY_LETTER,
    "investor_letter": DocumentType.MONTHLY_LETTER,
    "ddq": DocumentType.DDQ,
    "due_diligence_questionnaire": DocumentType.DDQ,
}


def classify_doc_type(
    content: str | bytes | Iterable[str],
    *,
    standard_library: StandardElementLibrary | None = None,
) -> DocumentType:
    """Classify a document from library IDs, then deterministic text cues."""

    text = _normalize_content(content)
    if not text:
        return DocumentType.UNKNOWN

    if standard_library is not None:
        library_match = _classify_library_doc_type(text, standard_library)
        if library_match is not DocumentType.UNKNOWN:
            return library_match

    for document_type, keywords in _DOCUMENT_TYPE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return document_type

    return DocumentType.UNKNOWN


def _classify_library_doc_type(
    text: str,
    standard_library: StandardElementLibrary,
) -> DocumentType:
    for library_doc_type in standard_library.doc_types():
        normalized_doc_type = _normalize_identifier(library_doc_type)
        if _library_doc_type_present(text, normalized_doc_type):
            document_type = _document_type_from_library_id(normalized_doc_type)
            if document_type is not DocumentType.UNKNOWN:
                return document_type
    return DocumentType.UNKNOWN


def _library_doc_type_present(text: str, normalized_doc_type: str) -> bool:
    variants = {
        normalized_doc_type,
        normalized_doc_type.replace("_", " "),
        normalized_doc_type.replace("_", "-"),
        _strip_stub_prefix(normalized_doc_type),
        _strip_stub_prefix(normalized_doc_type).replace("_", " "),
        _strip_stub_prefix(normalized_doc_type).replace("_", "-"),
    }
    return any(variant and _contains_delimited_term(text, variant) for variant in variants)


def _contains_delimited_term(text: str, term: str) -> bool:
    parts = [re.escape(part) for part in re.split(r"[\s_-]+", term.strip()) if part]
    if not parts:
        return False
    pattern = r"(?<![a-z0-9])" + r"[\s_-]+".join(parts) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def contains_delimited_term(text: str, term: str) -> bool:
    """Return whether a normalized term appears on token boundaries."""

    return _contains_delimited_term(text, term)


def _normalize_identifier(value: str) -> str:
    return value.strip().casefold().replace("-", "_").replace(" ", "_")


def _strip_stub_prefix(value: str) -> str:
    return value.removeprefix("stub_")


def _document_type_from_library_id(value: str) -> DocumentType:
    normalized = _strip_stub_prefix(value)
    direct = _STANDARD_LIBRARY_TYPE_ALIASES.get(normalized)
    if direct is not None:
        return direct
    tokens = tuple(token for token in normalized.split("_") if token)
    for alias, document_type in _STANDARD_LIBRARY_TYPE_ALIASES.items():
        alias_tokens = tuple(alias.split("_"))
        if _tokens_contain_alias(tokens, alias_tokens):
            return document_type
    return DocumentType.UNKNOWN


def _tokens_contain_alias(tokens: tuple[str, ...], alias_tokens: tuple[str, ...]) -> bool:
    if len(tokens) <= len(alias_tokens):
        return False
    starts_with_alias = tokens[: len(alias_tokens)] == alias_tokens
    ends_with_alias = tokens[-len(alias_tokens) :] == alias_tokens
    if starts_with_alias:
        return True
    if not ends_with_alias:
        return False
    return not any(token in {"no", "non", "not"} for token in tokens[: -len(alias_tokens)])


def _normalize_content(content: str | bytes | Iterable[str]) -> str:
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="ignore").casefold()
    if isinstance(content, str):
        return content.casefold()
    return "\n".join(content).casefold()
