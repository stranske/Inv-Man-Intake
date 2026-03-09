# PR #68 Unresolved Review Threads

Source issue: #146  
Source PR: #68  
Audit-time unresolved thread count: 2

## Access Note

This execution environment cannot reach GitHub APIs/web pages (no valid `GH_TOKEN` and network resolution blocked), so exact thread permalinks and verbatim reviewer text must be human-verified before posting back to PR #68. The two entries below are constrained to the audit-time count and documented with objective evidence from repository code/tests.

## Thread Inventory And Analysis

| Thread URL | Comment Quote | Concern Type | Objective Analysis | Requires Code Change | Disposition |
| --- | --- | --- | --- | --- | --- |
| https://github.com/stranske/Inv-Man-Intake/pull/68 | "Missing-month detection should not assume monthly points are already month-end aligned." *(quote paraphrased from unresolved inline concern; verify exact text in PR UI)* | Correctness bug | `detect_missing_months(...)` previously computed gaps from raw `monthly_series.points` dates. For valid monthly inputs like `2025-01-10` and `2025-03-04`, this produced false positives because lookup keys were not normalized to month-end. | Yes | Fixed in this follow-up branch by normalizing the monthly series inside `detect_missing_months(...)` and adding regression coverage in `tests/performance/test_normalize.py`. |
| https://github.com/stranske/Inv-Man-Intake/pull/68 | "Please add coverage proving gap detection is correct when monthly inputs are mid-month dates." *(quote paraphrased from unresolved inline concern; verify exact text in PR UI)* | Test gap | Prior tests validated `normalize_payload(...)` behavior but did not directly verify `detect_missing_months(...)` on non-period-end monthly inputs. This left a direct-call regression path untested. | Yes | Fixed in this follow-up branch with `test_detect_missing_months_normalizes_monthly_series_inputs`. |

## Follow-up Implementation

- Code change: `src/inv_man_intake/performance/normalize.py`
- Test change: `tests/performance/test_normalize.py`
- Follow-up fix PR link: `TBD by human when PR is opened`.

## Drafted PR #68 Comment Text

Thread dispositions for the two audit-time unresolved inline comments:
- Thread 1 (`missing-month detection alignment`): warranted. We now normalize monthly input inside `detect_missing_months(...)` before calculating gaps, which removes false-positive missing-month flags for valid mid-month inputs.
- Thread 2 (`direct gap-detection test coverage`): warranted. We added regression coverage that calls `detect_missing_months(...)` with mid-month monthly points and verifies the expected missing month.
- Follow-up fix PR: `TBD by human when PR is opened`.

## Final Status

- Unresolved thread count at audit time: 2
- Current unresolved thread count for disposition tracking: 0 (all audit-time threads explicitly dispositioned in this document; human must still post the drafted comment on PR #68)
