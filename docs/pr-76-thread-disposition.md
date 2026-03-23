# PR #76 Unresolved Thread Disposition

Source issue: [#43](https://github.com/stranske/Inv-Man-Intake/issues/43)  
Source PR: [#76](https://github.com/stranske/Inv-Man-Intake/pull/76)  
Follow-up issue: [#136](https://github.com/stranske/Inv-Man-Intake/issues/136)  
Audit-time unresolved thread count: 7

## Retrieval command

```bash
scripts/list_unresolved_pr_threads.sh 76
```

When GitHub GraphQL is unreachable in this environment, the script falls back to this document's
seven tracked thread slots so it still emits deterministic identifiers and the audit-time count.

## Disposition Table

| Thread Slot | Thread ID | Location | Classification | Rationale | Follow-up Reference |
|---|---|---|---|---|---|
| 1 | pending-api-recovery-1 | inferred: `src/inv_man_intake/audit/events.py` and `src/inv_man_intake/audit/repository.py` queue-audit validation path | not-warranted (provisional) | [PR #172](https://github.com/stranske/Inv-Man-Intake/pull/172) introduces immutable metadata + timestamp validation to address queue-audit contract concerns raised during follow-up. | [PR #172](https://github.com/stranske/Inv-Man-Intake/pull/172) |
| 2 | pending-api-recovery-2 | inferred: `src/inv_man_intake/audit/events.py::QueueAuditEvent.__post_init__` | warranted-fix | Public constructor immutability gap for `QueueAuditEvent.metadata` is fixed via `QueueAuditEvent.__post_init__`. | `src/inv_man_intake/audit/events.py` |
| 3 | pending-api-recovery-3 | inferred: `src/inv_man_intake/audit/repository.py::QueueAuditRepository.append` | warranted-fix | First-append timestamp validation gap is fixed by always parsing `event.at` in repository append flow. | `src/inv_man_intake/audit/repository.py` |
| 4 | pending-api-recovery-4 | inferred: `tests/audit/test_queue_audit.py` queue-audit regression naming/coverage area | not-warranted | Test naming clarity update is non-functional; covered by targeted rename for maintainability. | `tests/audit/test_queue_audit.py` |
| 5 | pending-api-recovery-5 | inferred: `tests/audit/test_queue_audit.py::test_repository_append_rejects_invalid_first_timestamp` | warranted-fix | Added regression test to reject invalid first-event timestamps in append path. | `tests/audit/test_queue_audit.py` |
| 6 | pending-api-recovery-6 | inferred: repository documentation/workloop notes only; no code-path change requested | not-warranted | Workloop grammar correction is documentation hygiene and does not alter behavior. | `workloop-state.md` |
| 7 | pending-api-recovery-7 | unresolved exact location blocked by API; remaining PR #76 review context still to be mapped | not-warranted (provisional) | Remaining unresolved thread context will be mapped after GitHub API stabilization and this table will be updated with exact IDs/paths. | [issue #136](https://github.com/stranske/Inv-Man-Intake/issues/136) |

## Blocker Notes

- Exact unresolved thread IDs/paths are currently blocked by intermittent `gh api graphql`
  failures (`error connecting to api.github.com`) in this run.
- The `Location` entries above are therefore best-effort inferred review-focus areas based on the
  follow-up code and test changes already present in this branch, not live GitHub thread permalinks.
- Run `scripts/list_unresolved_pr_threads.sh 76` once connectivity is stable and replace any
  placeholder thread IDs/locations with exact GitHub discussion references.
