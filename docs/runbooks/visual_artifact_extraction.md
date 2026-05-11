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

## Classification

`inv_man_intake.images.classifier.classify_visual_artifact` provides the baseline
informative-vs-boilerplate label for extracted artifacts. The classifier returns a
label, confidence score, stable reason codes, and rationale for downstream review
queue filtering.

See `docs/contracts/image_classification.md` for the heuristic contract and human
override path.

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

`VisualArtifactRepository.ensure_feedback_schema()` also creates
`visual_artifact_feedback` for human quality review. Feedback is keyed by
`artifact_id` + `reviewer`, so a reviewer can update the same artifact without
duplicating rows. Each record stores:
- `artifact_id`
- `is_informative`
- `quality_rank`
- `reviewer`
- `reviewed_at`
- `notes`

## Feedback Governance

Use `ImageFeedbackRecord` and `VisualArtifactFeedbackService` to capture analyst
review. `quality_rank` is an integer scale from 1 to 5:
- `1`: unusable or misleading visual
- `2`: low usefulness; mostly decorative or too unclear
- `3`: usable context but not decision-grade
- `4`: useful evidence with minor limitations
- `5`: high-value visual evidence for review or tuning

Repeated reviews from the same reviewer update the prior record. Preserve notes
when they explain disagreements between the classifier output and human judgment.

Generate tuning exports with `scripts/image_feedback_report.py`. The report summarizes
informative rate, rank distribution, timestamp range, and reviewer disagreement for stored
feedback records; see `docs/runbooks/image_feedback_tuning.md` for JSON and CSV commands.

## Limitations And Fallback Behavior

- PDF parsing is stream/object oriented and does not decode embedded image compression.
- Undecoded PDF image streams use generic binary MIME typing (`application/octet-stream`) unless the filter identifies a self-describing encoded format such as JPEG or JPEG 2000.
- PDF image objects whose stream bytes cannot be parsed are skipped rather than emitted as zero-byte artifacts.
- PDF page mapping relies on `/XObject` references. If a page link cannot be resolved, artifacts are retained with `page_number=0` fallback.
- PPTX extraction requires slide relationship files and media targets to exist in the archive.
- Unsupported extensions raise `UnsupportedVisualSourceError`; callers should route those files to non-visual extraction paths.
