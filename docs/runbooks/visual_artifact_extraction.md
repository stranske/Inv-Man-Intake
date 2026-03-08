# Visual Artifact Extraction (PDF/PPTX)

Issue: #24

## Scope

`inv_man_intake.images.extractor.extract_visual_artifacts` supports:
- PDF image object extraction (`/Subtype /Image` streams)
- PPTX slide image extraction (`ppt/slides/_rels/*.xml.rels` image relationships)

Each extracted artifact includes:
- Stable `artifact_id` derived from source location metadata and SHA-256 digest
- `sha256` for deduplication workflows
- Source linkage (`page_number` for PDF, `slide_number` for PPTX, plus `source_ref`)
- Deterministic `storage_path` suggestion for downstream persistence

## Persistence Contract

`VisualArtifactRepository` stores artifact catalog entries in `visual_artifacts` with:
- `artifact_id` (primary key)
- `document_id`
- `source_type`
- `source_page` / `source_slide`
- `source_ref`
- `storage_path`
- `sha256`
- `mime_type`
- `byte_size`
- `extracted_at`

## Limitations And Fallback Behavior

- PDF parsing is stream/object oriented and does not decode embedded image compression.
- PDF page mapping relies on `/XObject` references. If a page link cannot be resolved, artifacts are retained with `page_number=0` fallback.
- PPTX extraction requires slide relationship files and media targets to exist in the archive.
- Unsupported extensions raise `UnsupportedVisualSourceError`; callers should route those files to non-visual extraction paths.
