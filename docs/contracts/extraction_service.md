# ExtractionService Port

`ExtractionService` is the app-facing extraction port. Packet assembly, smoke
paths, and future operator UI code call `service.extract(source_doc_id, content)`
instead of importing concrete extractors.

## Backends

- `pyodide-light`: current Tier-A backend. It wraps the in-process PDF/PPTX
  providers and keeps the browser path dependency-light and no-egress.
- `localhost-service`: documented future adapter for a packaged local process,
  including Docling/OCR when local execution is permitted.
- `remote-service`: documented future adapter using the same API against a
  remote endpoint when egress is permitted.

The localhost and remote adapters are intentionally stubs in this repo until
those runtimes are allowed. Tests assert that a fake service backend can swap
with the Pyodide-light backend without consumer code changes.
