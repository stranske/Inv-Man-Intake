# Extraction Provider Contract

## Purpose

Define a stable provider interface so extraction backends can be swapped without changing orchestration logic.

## Provider Interface

Each canonical provider adapter must expose:
- `name` property (stable identifier)
- `extract(source_doc_id: str, content: bytes) -> ExtractedDocumentResult`

If a provider is multimodal-first, it should also expose:
- `extract_modalities(source_doc_id: str, content: bytes) -> ProviderExtractionOutput`
- Then call `normalize_provider_output(...)` to convert modality output into `ExtractedDocumentResult`

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

`ProviderExtractionOutput`:
- `source_doc_id`
- `provider_name`
- `text_blocks`
- `tables`
- `images`

## Conformance Requirements

1. Identity and traceability
- `provider_name` is non-empty and stable over time.
- `source_doc_id` is non-empty and carried through every emitted field.

2. Confidence constraints
- `ExtractedField.confidence` is always bounded in `[0.0, 1.0]`.
- `ExtractedTableCell.confidence`, when present, is bounded in `[0.0, 1.0]`.
- Unknown confidence must use placeholder `0.0`.

3. Source location requirements
- Canonical `ExtractedField` must include `source_page` with a non-negative integer.
- Unknown page must use placeholder `0`.
- `SourceLocation.source_doc_id` must match `ProviderExtractionOutput.source_doc_id`.

4. Determinism
- For identical `(source_doc_id, content)` input, output shape is deterministic.
- Field keys and ordering should remain stable for equivalent provider output.

## Validation Helpers

Future adapters should call these helpers before returning:
- `validate_provider_output(output)` for multimodal output
- `validate_extracted_document_result(result)` for canonical output

These helpers are defined in `inv_man_intake.extraction.providers.base` and are intended to catch
contract drift early in adapter development and in tests.

## Current Real-Byte Fixture Support

`PdfPrimaryExtractionProvider` supports committed, text-bearing PDF bytes for v1 smoke coverage. It
validates `%PDF-` framing, extracts literal content-stream text, emits canonical fields with
document/page provenance, and calls `validate_extracted_document_result(...)` before returning.

`PptxPrimaryExtractionProvider` supports committed, text-bearing PPTX bytes for v1 smoke coverage. It
validates Open Packaging Convention framing (`PK\x03\x04` magic plus a `ppt/presentation.xml` part),
reads DrawingML `<a:t>` text runs per slide, emits canonical fields with document/slide provenance
(1-based `source_page`), and calls `validate_extracted_document_result(...)` before returning. The
v1 smoke pipeline dispatches to this provider when a bundle's primary `file_name` ends in `.pptx`.

Secondary v1 roles such as XLSX are routed through the same provider/orchestrator boundary in smoke
coverage. Until a dedicated XLSX parser exists, unsupported secondary bytes produce deterministic
`ops_review` escalation rather than hard-coded extracted fields. Because OOXML containers
(`pptx`/`xlsx`/`docx`) share the `PK\x03\x04` ZIP magic, the escalation reason inspects the archive
contents to label the format rather than assuming a single extension.

## Fallback Adapter Implementation Notes

When adding a fallback parser/OCR adapter:

1. Implement either:
- A canonical `extract(...) -> ExtractedDocumentResult` adapter directly, or
- A multimodal `extract_modalities(...) -> ProviderExtractionOutput` adapter plus normalization.

2. Ensure placeholders are populated for missing metadata:
- Confidence placeholder: `0.0`
- Source page placeholder: `0`

3. Add/extend conformance tests to verify:
- Protocol runtime compatibility (`ExtractionProvider` / `MultiModalExtractionProvider`)
- Confidence range constraints
- Source metadata presence
- Baseline fixture output stability
