# Extraction Provider Contract

## Purpose

Define a stable provider interface so extraction backends can be swapped without changing orchestration logic.

## Provider Interface

Each provider must expose:
- `name` property (stable identifier)
- `extract(source_doc_id: str, content: bytes) -> ExtractedDocumentResult`

## Canonical Result Shape

`ExtractedDocumentResult`:
- `source_doc_id`
- `fields` (`tuple[ExtractedField, ...]`)
- `provider_name`

`ExtractedField`:
- `key`
- `value`
- `confidence`
- `source_doc_id`
- `source_page`

## Conformance Requirements

- Confidence is bounded in `[0.0, 1.0]`
- Every field includes source location metadata
- Output shape is deterministic for identical input
