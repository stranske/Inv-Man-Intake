# PR #84 Unresolved Review Threads

Source issue: #23  
Source PR: #84  
Follow-up issue: #121  
Follow-up PR: #148

## Thread Inventory

| Thread URL | Classification | Rationale | Disposition |
| --- | --- | --- | --- |
| https://github.com/stranske/Inv-Man-Intake/pull/84#discussion_r2901889973 | warranted-fix | The review correctly identified redundant counter semantics in quality metric aggregation. | Addressed in PR #84 commit `bc4b4b89314909a8897a554aa672f29e95c5d7c9` by removing redundant tracking and clarifying metric behavior. |
| https://github.com/stranske/Inv-Man-Intake/pull/84#discussion_r2901889981 | warranted-fix | The expected OCR-noise `performance_fee` key was not recoverable with the active regex behavior and caused mismatch noise. | Addressed in PR #84 commit `bc4b4b89314909a8897a554aa672f29e95c5d7c9` by updating fixture expectations to match supported extraction behavior. |
| https://github.com/stranske/Inv-Man-Intake/pull/84#discussion_r2901889989 | warranted-fix | The review correctly noted that CWD-relative test paths are brittle across invocation contexts. | Addressed in PR #84 commit `bc4b4b89314909a8897a554aa672f29e95c5d7c9` using file-relative path construction. |
| https://github.com/stranske/Inv-Man-Intake/pull/84#discussion_r2901889994 | not-warranted | The current runbook keeps scenario listing concise and readable without nested bullets; this is style-only with no correctness impact. | Documented as style preference; no additional code change required. |
| https://github.com/stranske/Inv-Man-Intake/pull/84#discussion_r2901889997 | warranted-fix | The original fallback counter condition was effectively non-informative for provider behavior. | Addressed in PR #84 commit `bc4b4b89314909a8897a554aa672f29e95c5d7c9` by comparing against the configured primary provider name. |

## Follow-up Implementation

- No additional follow-up code PR was required beyond PR #84 because warranted items were already fixed in that PR before merge.
- This follow-up PR (#148) documents final disposition and audit traceability.

## Disposition Comment Text (for PR #84)

Thread dispositions for previously unresolved review items:
- `discussion_r2901889973`: `warranted-fix` and addressed in PR #84 commit `bc4b4b89314909a8897a554aa672f29e95c5d7c9`.
- `discussion_r2901889981`: `warranted-fix` and addressed in PR #84 commit `bc4b4b89314909a8897a554aa672f29e95c5d7c9`.
- `discussion_r2901889989`: `warranted-fix` and addressed in PR #84 commit `bc4b4b89314909a8897a554aa672f29e95c5d7c9`.
- `discussion_r2901889994`: `not-warranted` as style-only documentation preference without functional impact.
- `discussion_r2901889997`: `warranted-fix` and addressed in PR #84 commit `bc4b4b89314909a8897a554aa672f29e95c5d7c9`.

## Final Status

- Unresolved thread count at audit time: 5
- Disposition comment: https://github.com/stranske/Inv-Man-Intake/pull/84#issuecomment-4020895038
- Current unresolved thread count on PR #84: 0
