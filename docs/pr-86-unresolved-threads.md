# PR #86 Unresolved Review Threads

Source issue: #22  
Source PR: #86  
Unresolved thread count at audit time: 4

## Classification Criteria

This follow-up classifies whether any additional work is still warranted now.

### Warranted Fix

- Security vulnerabilities or potential exploits
- Correctness bugs that could cause runtime errors
- Breaking changes to public APIs
- Data loss or corruption risks
- Performance issues with measurable impact (>10% degradation)

### Not-Warranted Disposition

- The requested behavior is already satisfied on `main`
- The thread is outdated and no further delta is justified
- Remaining feedback is documentation or style preference without functional impact
- The follow-up needed is audit/disposition closure, not a new code change

## Thread 1

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/86#discussion_r2901964241
- **Reviewer**: Copilot
- **File Path**: `docs/contracts/extraction_thresholds.md`
- **Line Number(s)**: 5-12
- **Comment Text**: "The docs call this a YAML config source, but the implementation currently only parses a restricted, line-oriented subset (single-level `key: value` + a `mandatory_fields:` block list). To prevent operators from writing valid YAML that will be misread (e.g. inline lists) and silently change policy behavior, consider documenting the supported subset/format constraints here, or updating `load_threshold_config` to use a proper YAML loader with schema validation."
- **Code Context**:
  ```text
  Thresholds are loaded from config/extraction_thresholds.yaml using load_threshold_config.
  The loader intentionally supports a strict subset:
  - scalar numeric keys must be plain key: value entries
  - mandatory_fields must use block-list syntax
  - inline list forms like mandatory_fields: [a, b] are rejected
  - unknown keys are rejected
  ```
- **Classification**: not-warranted disposition
- **Rationale**: Additional work is not warranted because current `main` already documents the exact restricted subset the reviewer asked to make explicit. The docs now tell operators which YAML forms are accepted and which are rejected, which resolves the original ambiguity that made the review comment actionable. There is no remaining correctness or safety gap that needs a separate follow-up patch.
- **Disposition**: Dispositioned as not-warranted for further follow-up; current `main` already documents the supported config subset and unsupported inline list forms.

## Thread 2

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/86#discussion_r2901964252
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/extraction/confidence.py`
- **Line Number(s)**: 33-66
- **Comment Text**: "`load_threshold_config()` is advertised as YAML, but the current line-based parser only supports a very narrow subset and can silently ignore valid YAML forms. For example, `mandatory_fields: [a, b]` (valid YAML) will not populate `mandatory_fields` at all, effectively disabling mandatory-field enforcement without an error. Consider switching to a real YAML parser (and validating the schema), or explicitly rejecting unsupported formats (e.g., raise if `mandatory_fields` appears on the same line as a value, or if unknown keys are present)."
- **Code Context**:
  ```text
  if line.startswith("mandatory_fields:"):
      raise ValueError("unsupported mandatory_fields format ...")
  ...
  if normalized_key not in {...}:
      raise ValueError(f"unknown threshold config key: {normalized_key}")
  ```
- **Classification**: not-warranted disposition
- **Rationale**: No additional patch is warranted because the branch history has already converged on the safer of the reviewer's two requested options: unsupported inline `mandatory_fields` syntax is rejected with a hard error, and unknown keys are rejected as well. That removes the silent-misparse behavior the thread was concerned about. Replacing the parser entirely with a general YAML loader would be a discretionary refactor, not required audit follow-up work.
- **Disposition**: Dispositioned as not-warranted for further follow-up; current `main` explicitly rejects the unsupported forms that previously posed the operational risk.

## Thread 3

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/86#discussion_r2901964265
- **Reviewer**: Copilot
- **File Path**: `src/inv_man_intake/extraction/confidence.py`
- **Line Number(s)**: 101-107
- **Comment Text**: "`key_field_coverage_ratio` is set to `1.0` when `key_fields` is empty, which makes `auto_pass_document` true and bypasses document gating entirely if a caller accidentally passes `()`. Given this is a policy enforcement hook, it would be safer to either raise on empty `key_fields` or treat empty as 0.0 coverage (forcing escalation) so misconfiguration can’t silently auto-pass."
- **Code Context**:
  ```text
  eligible_key_fields = [...]
  key_field_coverage_ratio = len(eligible_key_fields) / len(key_fields) if key_fields else 0.0
  auto_pass_document = key_field_coverage_ratio >= config.document_key_field_coverage_min
  ```
- **Classification**: not-warranted disposition
- **Rationale**: This thread does not warrant more follow-up because the risky behavior is already gone on `main`. Empty `key_fields` now yields `0.0` coverage instead of `1.0`, which forces escalation rather than silently auto-passing the document. The review concern was valid when raised, but it is now an outdated thread, not an unresolved engineering task that still needs a new fix PR.
- **Disposition**: Dispositioned as not-warranted for further follow-up; the empty-`key_fields` path already forces escalation on `main`.

## Thread 4

- **Thread URL**: https://github.com/stranske/Inv-Man-Intake/pull/86#discussion_r2901964291
- **Reviewer**: Copilot
- **File Path**: `tests/extraction/test_thresholds.py`
- **Line Number(s)**: 14-15
- **Comment Text**: "These tests load `config/extraction_thresholds.yaml` via a relative path (`Path(\"config/...\" )`), which makes the tests CWD-dependent. Other extraction tests resolve paths relative to `__file__` to avoid this (e.g. `tests/extraction/test_provider_contract.py:15-22`). Consider building the config path from `Path(__file__).resolve()` (or using a small helper fixture) so `pytest` works reliably when invoked from non-repo-root directories."
- **Code Context**:
  ```text
  _CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "extraction_thresholds.yaml"
  ```
- **Classification**: not-warranted disposition
- **Rationale**: No extra follow-up is justified because `main` already uses the file-relative path pattern the reviewer requested. The tests are no longer CWD-dependent, and the exact failure mode described in the review comment is already removed. That leaves only audit closure work: record the disposition and close the thread trail rather than reopen implementation work that has already been completed.
- **Disposition**: Dispositioned as not-warranted for further follow-up; the tests already resolve the config file relative to `__file__`.

## Final Status

- Total threads: 4
- Warranted fixes: 0
- Not-warranted dispositions: 4
- Remaining unresolved: 0 after posting per-thread disposition replies on PR #86
