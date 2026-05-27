# Workloop State — stranske/Inv-Man-Intake

## 2026-05-27T15:5XZ — opener (claude_code lane)

- **Repo:** stranske/Inv-Man-Intake
- **Issue:** [#462](https://github.com/stranske/Inv-Man-Intake/issues/462) — Add PPTX primary extraction provider so PPTX-primary packages reach scoring (priority:normal, repo-review-approved; approved-queue candidate)
- **Branch:** `claude/issue-462-pptx-primary-provider` (off `origin/main` `efb14aa`)
- **PR:** opened ready-for-review (see relay state)
- **Lane:** opener new-issue materialization
- **Next action:** wait_for_keepalive

### What changed
- New `src/inv_man_intake/extraction/providers/pptx_primary.py` — `PptxPrimaryExtractionProvider`: validates OPC framing (`PK\x03\x04` + `ppt/presentation.xml`), reads DrawingML `<a:t>` runs per slide, emits canonical fields with 1-based `source_page`, calls `validate_extracted_document_result`. Raises `UnsupportedDocumentFormatError` for non-PPTX / bare ZIP.
- Exported the provider from `providers/__init__.py` (import + `__all__`).
- `v1_smoke.py`: primary extraction is now bundle-driven — `run_v1_smoke_pipeline` resolves the primary `file_name` from the registered document and `_run_extraction_smoke` dispatches `_select_primary_provider` (`.pptx` → PPTX provider, else PDF). Generalized `_pdf_provider_extractor` → `_provider_extractor` (typed `ExtractionProvider`). Fixed the secondary-bytes reason: `PK\x03\x04` now inspects the archive (`_ooxml_zip_kind`) to label pptx/xlsx/docx instead of hardcoding `xlsx`.
- New fixture `tests/fixtures/extraction/harborline_strategy_review.pptx` (2 slides, key-field phrases).
- New tests `tests/extraction/test_pptx_primary_provider.py`, `tests/v1/test_smoke_pptx_primary.py`.
- Updated `tests/readiness/test_throughput_readiness.py` expected `escalation_count` 6 → 5 (PPTX primary now reaches scoring rather than escalating — the issue's intent).
- Updated `docs/contracts/extraction_provider_contract.md` "Current Real-Byte Fixture Support".

### Spec reconciliation (noted for keepalive/reviewer)
- Issue Task 1 said `confidence=0.0`, but AC2 requires `threshold_decision.escalate is False`. With the fixed threshold config in `run_v1_smoke_pipeline`, escalate=False needs ≥4/5 key fields at confidence ≥0.75 (mandatory `operations.aum` ≥0.60). The PPTX provider assigns high per-field confidences (structured DrawingML text), so the doc auto-passes. Acceptance criteria take precedence over the inline `confidence=0.0` detail.
- Issue Task 5 said return `format: pptx` for the `PK\x03\x04` branch, but the PDF bundle's secondary is genuinely `xlsx` and `test_document_byte_provider.py` pins that string. Instead of mislabeling xlsx as pptx, the reason inspects archive contents (correct per-format label). AC3 (`rg "format: xlsx"` → no literal) holds because the reason is an f-string; runtime value stays `xlsx` for the xlsx secondary.

### Validation (local, `PYTHONPATH=src`)
- `pytest tests/extraction/test_pptx_primary_provider.py` → 4 passed (AC1)
- `pytest tests/v1/test_smoke_pptx_primary.py` → 1 passed (AC2)
- `grep "format: xlsx" src/inv_man_intake/v1_smoke.py` → no matches (AC3)
- `grep PptxPrimaryExtractionProvider src/.../providers/__init__.py` → import + `__all__` (AC4)
- `python -m inv_man_intake.readiness.throughput` → exit 0, status pass, score_count 2, escalation_count 5 (AC5)
- Full suite: 552 passed; `ruff check`/`ruff format --check` clean; `mypy` (strict, 68 files) clean.
