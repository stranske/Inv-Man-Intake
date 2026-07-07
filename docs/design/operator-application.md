# Operator Application Design

Issue: [#718](https://github.com/stranske/Inv-Man-Intake/issues/718)

## Decision

Inv-Man-Intake remains a headless backend. The operator application is a local
consumer of committed contracts and run artifacts, not a new production API
inside `src/inv_man_intake`.

The first application surface should be the Tier-A local operator app tracked by
[#723](https://github.com/stranske/Inv-Man-Intake/issues/723). It can reuse the
existing browser-demo/Pyodide posture while graduating from fixture inspection to
operator workflow review. It must consume:

- `src/inv_man_intake/validation_queue_api.py` for queue filtering, paging,
  owner-role, state, SLA, and escalation views.
- `src/inv_man_intake/run.py` artifacts, especially `run.json`,
  `metadata.json`, `threshold-summary.json`, `explainability.json`, and
  `manifest.json`.
- Existing queue state contracts from `src/inv_man_intake/workflow_validation.py`
  and `docs/contracts/queue_states.md`.

## Users

- Analyst: reviews pending or escalated fields, sees why a manager package needs
  attention, and records corrections through the existing validation workflow.
- Operations reviewer: monitors queue health, stale items, ownership, SLA, and
  run artifact completeness before a manager profile moves downstream.
- Local operator: runs the intake on a work PC and inspects outputs without
  sending proprietary manager documents outside the local data zone.

## Headless Boundary

The application must treat this repo as a library and artifact producer. It may
call public Python APIs and read output artifacts, but it must not require a new
FastAPI, Gradio, or cloud service server in `src/inv_man_intake`.

The local app can live under `app/` or a thin external shell. If it stays in this
repo, it remains a consumer of the headless package. The backend package should
continue to expose deterministic functions, dataclasses, and run artifacts that
other analyst queues can consume.

## Local-First Data Zone

The operator app is local-first and runs on the work PC. It must not upload raw documents,
raw extracted field values, or proprietary manager identifiers to an external
service by default.

Required checks for child implementation:

- LangSmith and fleet telemetry stay disabled for local proprietary runs unless
  the operator explicitly enables a redacted telemetry mode.
- `run.json` remains in an operator-supplied output directory and is not written
  to the fleet telemetry sink.
- The app does not fetch external runtime code when loading proprietary package
  artifacts.
- Any LLM path must go through the egress guard from
  [#724](https://github.com/stranske/Inv-Man-Intake/issues/724).

## Views

The first operator workflow should include:

- Run list: package id, firm/fund ids, status, artifact manifest, score, warning
  count, and run timestamp.
- Queue triage: validation state, owner role, owner id, SLA age, escalation
  reason, and filtering backed by `ValidationQueueQuery`.
- Package detail: document versions, extracted fields, confidence state,
  threshold decision, explainability, red-flag reason, and evidence refs.
- Correction review: latest corrections and calibration impact, backed by
  [#711](https://github.com/stranske/Inv-Man-Intake/issues/711).
- Recommendation inbox: read-only assistant recommendations from
  [#725](https://github.com/stranske/Inv-Man-Intake/issues/725), never direct
  config writes.

## Child Issue Map

[#718](https://github.com/stranske/Inv-Man-Intake/issues/718) is the planning
epic. Its implementation children are:

- [#721](https://github.com/stranske/Inv-Man-Intake/issues/721): standard
  element-library contract and classify/split consumption.
- [#722](https://github.com/stranske/Inv-Man-Intake/issues/722): packet-level
  ingestion pipeline and cross-document reconciliation.
- [#723](https://github.com/stranske/Inv-Man-Intake/issues/723): operator app
  MVP.
- [#724](https://github.com/stranske/Inv-Man-Intake/issues/724): LLM egress
  guard and redaction boundary.
- [#725](https://github.com/stranske/Inv-Man-Intake/issues/725): intake
  improvement assistant.
- [#726](https://github.com/stranske/Inv-Man-Intake/issues/726): PPM
  standard/non-standard evaluator.
- [#727](https://github.com/stranske/Inv-Man-Intake/issues/727): return-stream
  non-standard characterizer.

## Verification

The operator app MVP should have a named gate that loads committed fixture
artifacts, renders the queue and package detail views, and asserts:

- `ValidationQueueQuery` drives state/owner/SLA filters.
- The run artifact manifest resolves every displayed artifact.
- No external document call is made by default.
- Assistant recommendations are displayed as read-only proposals.
