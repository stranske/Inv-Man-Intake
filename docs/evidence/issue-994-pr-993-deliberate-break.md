# Issue #994: PR #993 deliberate-break evidence

This is a fresh replay against `main` at merge commit
`209f989b024d2deb420edfaedf596cd1b8e8db0e`; it is not reconstructed output
from PR #993. The replay was run on 2026-09-29 with Python 3.12.2 and Node
available to the production-script harness.

## Deliberate break

Only the production fork fallback predicate in
`.github/workflows/pr-00-gate.yml` was disabled:

```diff
-              const readOnlyForkToken =
-                error?.status === 403 && isForkPullRequest && !hitRateLimit;
+              const readOnlyForkToken =
+                false && error?.status === 403 && isForkPullRequest && !hitRateLimit;
```

The named acceptance command exited 1 and identified the six fork/deleted-fork
cases that depend on the fallback:

```text
$ python -m pytest --no-cov tests/test_gate_commit_status_fork_tolerance.py -q
============================= test session starts ==============================
platform darwin -- Python 3.12.2, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/teacher/.codex/automations/pd-workloop-resume/worktrees/Inv-Man-Intake-issue-994
configfile: pyproject.toml
plugins: cov-7.1.0, xdist-3.8.0, rerunfailures-16.3, datadir-1.8.0, typeguard-4.5.1, asyncio-1.3.0, pytest_httpserver-1.1.3, hypothesis-6.155.7, regressions-2.11.0, Faker-40.39.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 10 items

tests/test_gate_commit_status_fork_tolerance.py FFFFFF....               [100%]

=================================== FAILURES ===================================
________________ test_fork_read_only_403_does_not_fail_the_gate ________________

    def test_fork_read_only_403_does_not_fail_the_gate(outcomes: dict[str, Any]) -> None:
>       assert outcomes["fork_read_only"]["threw"] is None
E       AssertionError: assert {'status': 403, 'message': 'Resource not accessible by integration'} is None

tests/test_gate_commit_status_fork_tolerance.py:199: AssertionError
_______________ test_fork_read_only_403_reports_the_real_verdict _______________

    def test_fork_read_only_403_reports_the_real_verdict(outcomes: dict[str, Any]) -> None:
        case = outcomes["fork_read_only"]
        warning = " ".join(case["warnings"])
        summary = " ".join(case["summaryRaw"])
>       assert "read-only" in warning
E       AssertionError: assert 'read-only' in ''

tests/test_gate_commit_status_fork_tolerance.py:207: AssertionError
______________ test_fork_read_only_403_preserves_failure_verdict _______________

    def test_fork_read_only_403_preserves_failure_verdict(
        outcomes: dict[str, Any],
    ) -> None:
        case = outcomes["fork_read_only_failure"]
        warning = " ".join(case["warnings"])
        summary = " ".join(case["summaryRaw"])
>       assert case["threw"] is None
E       AssertionError: assert {'status': 403, 'message': 'Resource not accessible by integration'} is None

tests/test_gate_commit_status_fork_tolerance.py:221: AssertionError
__ test_fork_read_only_403_fails_closed_for_other_non_success_verdicts[error] __

    @pytest.mark.parametrize("state", ["error", "pending"])
    def test_fork_read_only_403_fails_closed_for_other_non_success_verdicts(
        outcomes: dict[str, Any], state: str
    ) -> None:
        case = outcomes[f"fork_read_only_{state}"]
>       assert case["threw"] is None
E       AssertionError: assert {'status': 403, 'message': 'Resource not accessible by integration'} is None

tests/test_gate_commit_status_fork_tolerance.py:233: AssertionError
_ test_fork_read_only_403_fails_closed_for_other_non_success_verdicts[pending] _

    @pytest.mark.parametrize("state", ["error", "pending"])
    def test_fork_read_only_403_fails_closed_for_other_non_success_verdicts(
        outcomes: dict[str, Any], state: str
    ) -> None:
        case = outcomes[f"fork_read_only_{state}"]
>       assert case["threw"] is None
E       AssertionError: assert {'status': 403, 'message': 'Resource not accessible by integration'} is None

tests/test_gate_commit_status_fork_tolerance.py:233: AssertionError
_____________ test_deleted_fork_read_only_403_reports_the_verdict ______________

    def test_deleted_fork_read_only_403_reports_the_verdict(
        outcomes: dict[str, Any],
    ) -> None:
        case = outcomes["deleted_fork_read_only"]
        warning = " ".join(case["warnings"])
>       assert case["threw"] is None
E       AssertionError: assert {'status': 403, 'message': 'Resource not accessible by integration'} is None

tests/test_gate_commit_status_fork_tolerance.py:243: AssertionError
=========================== short test summary info ============================
FAILED tests/test_gate_commit_status_fork_tolerance.py::test_fork_read_only_403_does_not_fail_the_gate
FAILED tests/test_gate_commit_status_fork_tolerance.py::test_fork_read_only_403_reports_the_real_verdict
FAILED tests/test_gate_commit_status_fork_tolerance.py::test_fork_read_only_403_preserves_failure_verdict
FAILED tests/test_gate_commit_status_fork_tolerance.py::test_fork_read_only_403_fails_closed_for_other_non_success_verdicts[error]
FAILED tests/test_gate_commit_status_fork_tolerance.py::test_fork_read_only_403_fails_closed_for_other_non_success_verdicts[pending]
FAILED tests/test_gate_commit_status_fork_tolerance.py::test_deleted_fork_read_only_403_reports_the_verdict
========================= 6 failed, 4 passed in 0.35s ==========================
```

## Exact restoration

The deliberate mutation was reverted exactly. The same named acceptance command
then exited 0:

```text
$ python -m pytest --no-cov tests/test_gate_commit_status_fork_tolerance.py -q
============================= test session starts ==============================
platform darwin -- Python 3.12.2, pytest-9.1.1, pluggy-1.6.0
rootdir: /Users/teacher/.codex/automations/pd-workloop-resume/worktrees/Inv-Man-Intake-issue-994
configfile: pyproject.toml
plugins: cov-7.1.0, xdist-3.8.0, rerunfailures-16.3, datadir-1.8.0, typeguard-4.5.1, asyncio-1.3.0, pytest_httpserver-1.1.3, hypothesis-6.155.7, regressions-2.11.0, Faker-40.39.0, anyio-4.13.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 10 items

tests/test_gate_commit_status_fork_tolerance.py ..........               [100%]

============================== 10 passed in 0.31s ==============================
```

Restoration hygiene also passed:

```text
$ git diff --exit-code -- .github/workflows/pr-00-gate.yml tests/test_gate_commit_status_fork_tolerance.py
```

The command emitted no output and exited 0, proving the deliberate-break
workflow and test changes were fully restored. The only deliverable change is
this evidence record.
