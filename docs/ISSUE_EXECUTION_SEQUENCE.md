# Issue Execution Sequence (Initial 10)

Date: March 1, 2026
Purpose: Dependency-ordered execution list for the first 10 implementation issues.

## Sequence Order

1. #16 `Intake contract and metadata schema`
2. #28 `Core firm/fund/document schema migration`
3. #17 `Document store adapter + versioning primitives`
4. #29 `Field provenance and correction-history schema`
5. #30 `Core repository layer and schema contract docs`
6. #18 `Ingestion lifecycle orchestration and status transitions`
7. #44 `LangSmith tracing wrappers and context propagation`
8. #20 `Extraction provider interface and primary adapter`
9. #21 `Fallback retry orchestration and escalation routing`
10. #22 `Confidence thresholds config and enforcement`

## Dependency Notes

- #16 precedes #18/#20 because intake contract defines package shape.
- #28 precedes #29/#30 because relational core tables must exist first.
- #17 and #29 feed #18 (ingestion lifecycle needs versioning and provenance persistence).
- #44 starts early so tracing hooks are available in extraction/integration code.
- #20 precedes #21 and #22 because orchestrator logic depends on provider contract.
- #21 precedes #22 for clean separation of retry path then policy thresholds.

## Execution Checklist

- [ ] Open issue-linked PR for #16 and implement scope
- [ ] Open issue-linked PR for #28 and implement scope
- [ ] Open issue-linked PR for #17 and implement scope
- [ ] Open issue-linked PR for #29 and implement scope
- [ ] Open issue-linked PR for #30 and implement scope
- [ ] Open issue-linked PR for #18 and implement scope
- [ ] Open issue-linked PR for #44 and implement scope
- [ ] Open issue-linked PR for #20 and implement scope
- [ ] Open issue-linked PR for #21 and implement scope
- [ ] Open issue-linked PR for #22 and implement scope

## PR Workloop Rule

After each issue push:
- Move immediately to the next issue; do not idle waiting for CI.
- Sweep all open PRs for inline comments, merge conflicts, and failing checks.
- Push fixes for each affected PR before continuing deeper backlog work.
