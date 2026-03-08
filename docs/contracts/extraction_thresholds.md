# Extraction Thresholds (v1)

Issue: #22

## Config Source

Thresholds are loaded from [`config/extraction_thresholds.yaml`](../../config/extraction_thresholds.yaml) using `load_threshold_config` in `src/inv_man_intake/extraction/confidence.py`.

## Threshold Semantics

- `field_auto_accept_min` (0.85)
  - A field is marked auto-acceptable when `field.confidence >= field_auto_accept_min`.
- `key_field_confidence_min` (0.75)
  - A key field counts toward document coverage when `field.confidence >= key_field_confidence_min`.
- `document_key_field_coverage_min` (0.80)
  - Document auto-pass requires key-field coverage ratio `>= document_key_field_coverage_min`.
- `mandatory_field_min` (0.60)
  - Any configured mandatory field below this value forces escalation.
- `mandatory_fields`
  - Required keys that must exist and meet `mandatory_field_min`.

## Escalation Rules

Escalation is deterministic and reason-coded:
- `missing_mandatory_field:<field_key>` when a mandatory field is absent.
- `confidence_below_threshold:<field_key>` when a mandatory field falls below floor.
- `low_key_field_coverage` when mandatory checks pass but document coverage fails.

## Orchestration Attachment

`attach_threshold_summary` appends document-level confidence policy fields:
- `confidence.document.key_field_coverage_ratio`
- `confidence.document.auto_pass`
- `confidence.document.escalation_reason`

These fields allow downstream orchestration/queue routing to read threshold outcomes without re-computing policy logic.
