# Intake Improvement Assistant Design

Issue: [#718](https://github.com/stranske/Inv-Man-Intake/issues/718)

## Decision

The intake improvement assistant is a read-only analysis layer over local run,
queue, correction, scoring, and readiness signals. It recommends improvements to
thresholds, weights, parser coverage, document-type profiles, and operator
workflow priorities. It never edits `config/*`, mutates artifacts, or applies a
policy change automatically.

The implementation child is
[#725](https://github.com/stranske/Inv-Man-Intake/issues/725). The egress and
privacy precondition is
[#724](https://github.com/stranske/Inv-Man-Intake/issues/724).

## Inputs

The assistant reads structured local signals only:

- `run.json`, `threshold-summary.json`, `explainability.json`, and
  `manifest.json` from `src/inv_man_intake/run.py`.
- Queue rows and escalation reasons from
  `src/inv_man_intake/validation_queue_api.py`.
- Correction history from `CorrectionRecord` in
  `src/inv_man_intake/data/provenance.py`.
- Score contributions and red-flag reasons from
  `src/inv_man_intake/scoring/contracts.py`.
- Calibration reports from
  [#711](https://github.com/stranske/Inv-Man-Intake/issues/711).
- Extraction drift reports from
  [#714](https://github.com/stranske/Inv-Man-Intake/issues/714).
- Weight sensitivity reports from
  [#716](https://github.com/stranske/Inv-Man-Intake/issues/716).
- Document-type threshold profiles from
  [#717](https://github.com/stranske/Inv-Man-Intake/issues/717).

## Recommendation Contract

Each recommendation should be evidence-cited and structured:

- `target`: threshold, scoring weight, parser/doc-type profile, queue workflow,
  or documentation.
- `evidence_refs`: run artifact ids, queue item ids, correction ids, score
  contribution names, or report row ids.
- `rationale`: why this change improves intake quality.
- `risk`: expected false-positive, false-negative, review-load, or local data
  zone risk.
- `suggested_action`: a human-readable proposal, not a patch.
- `requires_human_apply`: always `true`.

The assistant output can later feed a HITL apply loop, but that loop must still
require explicit human approval before any config file changes.

## Local-First And Egress Rules

Default mode is deterministic local analysis. It may use template rules or a
local model over redacted summaries. Any frontier API call must route through
`send_to_llm` from the egress guard and must satisfy:

- explicit per-call consent;
- zero-retention and BAA-eligible provider policy;
- redaction of raw document text, proprietary identifiers, and unsupported
  non-JSON values;
- append-only JSONL audit logging;
- no raw document payload egress.

No child issue may bypass the egress guard by calling a provider SDK directly.

## No Auto-Apply

The assistant must never write `config/extraction_thresholds.yaml`,
`config/scoring_weights/*`, or generated run artifacts. It may write a separate
recommendation artifact under an operator-supplied output directory.

Any future apply path must be a separate HITL command that:

- reads a recommendation artifact;
- shows the diff or generated candidate change to the operator;
- requires explicit approval;
- records approval metadata;
- validates the named gate before saving a config change.

## Dependency Order

The assistant becomes useful only after its upstream analytics exist:

1. [#711](https://github.com/stranske/Inv-Man-Intake/issues/711): correction
   calibration closes the extraction feedback loop.
2. [#714](https://github.com/stranske/Inv-Man-Intake/issues/714): drift reports
   show stale extraction or source-quality regressions.
3. [#716](https://github.com/stranske/Inv-Man-Intake/issues/716): weight
   sensitivity reports show ranking instability and approval impact.
4. [#717](https://github.com/stranske/Inv-Man-Intake/issues/717): document-type
   profiles make threshold recommendations document-aware.
5. [#724](https://github.com/stranske/Inv-Man-Intake/issues/724): LLM egress
   guard provides the only approved outbound LLM boundary.
6. [#725](https://github.com/stranske/Inv-Man-Intake/issues/725): read-only
   assistant over the above signals.

## Verification

The assistant implementation should include a named gate that builds a
recommendation from fixture artifacts and asserts:

- each recommendation has at least one evidence ref;
- `requires_human_apply` is true;
- no `config/*` file is written;
- no external document call is made by default;
- any LLM-backed path is impossible without egress-guard consent and provider
  policy.
