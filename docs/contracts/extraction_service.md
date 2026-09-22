# ExtractionService Port

`ExtractionService` is the app-facing extraction port. Packet assembly, smoke
paths, and future operator UI code call `service.extract(source_doc_id, content)`
instead of importing concrete extractors.

## Backends

- `pyodide-light`: current Tier-A backend. For PDFs it selects the pinned
  `inv-man-intake[extraction-doc-lineage]` adapter when installed, with
  page-specific text-layer/OCR pointers. It falls back to the historical
  `pdf-primary` fixture parser only when that optional package is absent.
  PPTX continues through the in-process primary provider; no network egress is
  added. A Doc-Lineage result with unreadable pages raises
  `IncompleteExtractionError` with coverage counts and readable partial fields.
- `doc-lineage-local`: the historical `build_docling_service` factory now uses
  the same Doc-Lineage PDF/OCR adapter so there is one production OCR path.
  Its `do_ocr` argument remains accepted for compatibility; OCR fallback is
  always enabled. The Tesseract executable is a local runtime prerequisite for
  recognizing scanned pages.
- `localhost-service`: documented future adapter for a packaged local process,
  including Docling/OCR when local execution is permitted.
- `remote-service`: documented future adapter using the same API against a
  remote endpoint when egress is permitted.

The localhost and remote adapters are intentionally stubs in this repo until
those runtimes are allowed. Tests assert that a fake service backend can swap
with the Pyodide-light backend without consumer code changes.
