# Image Classification Contract

Issue: #25

## Scope

`inv_man_intake.images.classifier.classify_visual_artifact` provides the baseline
informative-vs-boilerplate label for extracted `VisualArtifact` records. It is a
deterministic heuristic classifier intended to prioritize review queues before any
model-backed image classifier exists.

Each classification returns:

- `artifact_id`
- `label`: `informative` or `boilerplate`
- `confidence`: a bounded `0.0` to `1.0` score
- `reason_codes`: stable machine-readable heuristic reasons
- `rationale`: a short analyst-readable explanation

## Heuristic Signals

Informative signals include:

- chart, table, benchmark, performance, risk, return, exposure, and related
  investment-analysis terms
- numeric chart markers such as quarters, years, and percentage values
- higher text density in the extracted artifact preview

Boilerplate signals include:

- logo, disclaimer, copyright, confidential, trademark, and offer/distribution
  language
- source references such as logo, banner, footer, or masthead
- very low text density or very small payloads

## Override Path

Human review tools should treat this classifier as a first-pass routing signal, not
as final truth. When an analyst corrects a label, persist the override alongside:

- `artifact_id`
- corrected label
- reviewer identifier
- override reason
- review timestamp

Downstream tuning reports should compare overrides against `reason_codes` so common
false positives and false negatives can be promoted into classifier fixtures.

## Limitations

- The classifier does not decode raster pixels or perform OCR.
- Binary-only chart screenshots without embedded text may fall back to low-density
  boilerplate until OCR/model features are added.
- The confidence score is calibrated for queue ordering, not statistical certainty.
