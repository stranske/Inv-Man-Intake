# PR #80 Unresolved Review Threads

Source issue: #39  
Source PR: #80  
Follow-up issue: #125  
Follow-up PR: #168

## Thread Disposition

| Thread ID | Thread URL | Classification | Disposition |
| --- | --- | --- | --- |
| `PRRT_kwDORbgIAs5y2J26` | https://github.com/stranske/Inv-Man-Intake/pull/80#discussion_r2901579956 | warranted-fix | Updated JSON example in [`docs/runbooks/scoring_calibration.md`](docs/runbooks/scoring_calibration.md) to show a list payload. |
| `PRRT_kwDORbgIAs5y2J3A` | https://github.com/stranske/Inv-Man-Intake/pull/80#discussion_r2901579963 | warranted-fix | Updated duplicate-entry error text in [`src/inv_man_intake/scoring/regression.py`](src/inv_man_intake/scoring/regression.py) to use `asset_class=` consistently. |
| `PRRT_kwDORbgIAs5y2J3G` | https://github.com/stranske/Inv-Man-Intake/pull/80#discussion_r2901579969 | not-warranted disposition | Removing `workloop-state.md` is out of scope for issue #125 because it is historical repo policy/workflow hygiene, not a bounded PR #80 thread fix. |
| `PRRT_kwDORbgIAs5y2J3P` | https://github.com/stranske/Inv-Man-Intake/pull/80#discussion_r2901579978 | not-warranted disposition | Empty bullet items were in historical PR #80 context; current `workloop-state.md` no longer contains the cited noise and no additional production-code change is needed. |

## Notes

- Thread inventory captured via `gh api graphql` for PR #80.
- This follow-up PR records either a concrete fix or explicit disposition rationale for each unresolved thread from audit time.
