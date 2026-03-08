# Inv-Man-Intake Plan v1 (Draft)

Date: March 1, 2026
Status: Updated after stakeholder clarifications

## 1) Initial Plan From Stakeholder Responses

### Why
Build the first production-capable intake-to-scoring pipeline for investment manager packages, with firm -> fund -> document hierarchy, confidence-aware extraction, and analyst/ops triage support.

### Confirmed Scope (v1)
- Deliver from document intake through priority scoring.
- Primary user personas: analysts and ops.
- Expected starting throughput: 10-15 manager packages per week.
- Asset classes in first wave:
  - Equity market neutral
  - Quant
  - Multi-strat
  - Credit long/short
  - Macro
  - Trend following
  - Credit relative value
  - Activist

### In-Scope Inputs
- Primary: PDF, PPTX
- Secondary: XLSX, email notes, Word docs

### Processing and Review Stance
- Fully automated default path where possible.
- Human review queue exists for rough edges, exceptions, and conflict resolution.
- Retry policy: if extraction/parsing fails, retry with alternate tool; escalate to human if still failing.

### Data and Provenance Decisions
- Core hierarchy: firm -> fund -> document.
- Field completeness policy: do not lock hard mandatory fields yet (except monthly return requirement in performance); converge after real data intake.
- Provenance requirement for extracted values: source document + page.
- Versioning policy: date-based versioning for documents and corrected fields.

### Performance and Credibility Decisions
- Track record source will usually be manager-supplied and must be clearly documented.
- Required frequencies: monthly, quarterly, annual.
- Only strict mandatory performance input: monthly returns.
- High-priority (not mandatory at launch): Sharpe, Sortino, information ratio, volatility, drawdown, and correlation vs key benchmarks.
- Conflict rule: prefer Excel data over non-Excel documents; escalate to human if conflicting data exceeds 5% of comparable points.

### Enrichment and Scoring Decisions
- No external enrichment signals in v1.
- Priority scoring must be asset-class-specific.
- Score explainability is required.

### Platform and Ops Decisions
- One repository (single repo strategy).
- Interface/spec docs to live under `docs/`.
- No heavy compliance/security requirements at first.
- Add LangSmith tracing from the start.
- CI baseline: keep current Workflows default gates (lint, typecheck, tests, >=80% coverage); do not add repo-specific required checks initially.

## 2) Clarifications Resolved

Stakeholder clarifications received on March 1, 2026:

1. Outcome ranking (highest to lowest)
   1. Parsing accuracy
   2. Analyst trust
   3. Triage quality
   4. Cycle time
   5. Throughput

2. Service target
- Same business day from intake to scored output.

3. Throughput unit
- 10-15 manager packages per week.

4. Validation queue ownership
- Analyst first-touch triage model.

5. Extraction acceptance thresholds (approved for v1 start)
- Field-level auto-accept confidence >= 0.85
- Document-level auto-pass if >= 80% key fields extracted with >= 0.75 confidence
- Auto-escalate if any mandatory class-specific field is < 0.60 confidence

## 3) Updated Plan (Post-Clarification)

This section replaces previous provisional assumptions with confirmed decisions.

### Confirmed Delivery Parameters
- Throughput assumption: 10-15 packages per week.
- Service target: same business day from intake to scored output.
- Queue ownership: analyst first-touch triage.
- Extraction thresholds: confirmed and approved as listed in Section 2.

### Workstreams
1. Intake and document registry
- Land multi-format ingestion (PDF, PPTX, XLSX, DOCX, email notes).
- Build document versioning with hash + received date.
- Persist provenance metadata (document/page pointers).

2. Extraction and parsing quality pipeline
- Add OCR/layout + table/image extraction with retry fallback.
- Add confidence scoring and key-field completeness checks.
- Route failures/low-confidence items to validation queue.

3. Image intelligence and feedback loop
- Separate boilerplate vs informative graphics.
- Capture user feedback on image usefulness and quality ranking.
- Store feedback events for iterative model/rule improvements.

4. Data model and storage contracts
- Implement firm -> fund -> document core schema and contract docs.
- Add flexible field nullability and date-based correction history.
- Capture source metadata at field-level.

5. Performance normalization and conflict handling
- Ingest monthly/quarterly/annual returns with monthly mandatory.
- Compute prioritized metrics (vol, drawdown, Sharpe, Sortino, IR, correlations).
- Enforce Excel precedence and >5% conflict escalation.

6. Asset-class-specific scoring and outputs
- Build configurable weight sets by asset class.
- Implement explainable score breakdown.
- Produce queue-ready summary artifacts for analysts/ops.

7. Analyst/Ops workflow and UI integration
- Build validation queue states and analyst-first ownership workflow.
- Add triage dashboard contracts and export interfaces.

8. Observability and operational baseline
- Wire LangSmith tracing across ingestion/extraction/scoring paths.
- Keep CI posture aligned with Workflows defaults.

## 4) Delivery Structure (Thorough Decomposition)

To avoid under-scoping, implementation work is structured as:
- 1 umbrella epic covering v1.
- 8 workstream epics (one per major capability area).
- Multiple detailed child implementation issues under each workstream epic (contracts, services, tests, docs, and ops hooks).

This supports parallel execution without losing traceability between high-level goals and concrete deliverables.

## 5) Milestone Shape
- Milestone A: Intake, registry, and core schema contracts
- Milestone B: Extraction confidence, validation queue, and image feedback primitives
- Milestone C: Performance normalization and conflict policy automation
- Milestone D: Asset-class scoring, explainability, and triage outputs
