# Issue #1018 verification

- [x] CLI/queue/API/smoke/manifest suite passes after formatting: **139 passed**,
  including all existing tests in these areas. Focused API replay/schema tests:
  **41 passed**, 10 deselected. See [suite output](regression-suite.txt) and
  [focused output](api-replay-schema.txt).
- [x] Verify the artifact-write disconnect evidence. Disconnecting the actual
  production artifact write produces **4 failed**;
  restoring the source byte-for-byte produces **4 passed**. Source and final CLI
  test SHA-256 values are recorded in [the proof](queue-write-proof.json), beside
  the [failure](queue-write-red.txt) and [restoration](queue-write-green.txt)
  transcripts. Only trailing whitespace was removed from the failure transcript.
  The prior evidence was committed in `d495bc4`; these transcripts cover the added
  saved-review replay regressions. The workspace `.git` remains read-only.
- [x] Focused mypy passes for `run.py`, `v1_smoke.py`, `workflow_validation.py`,
  and `run_manifest.py`. Repository-wide Ruff, Black, and diff checks pass;
  see [static checks](static-checks.txt). The existing smoke transition test is
  unchanged and passes as part of the suite.
- [x] Both escalating and accepted-policy bundles reload through the real CLI.
  The CLI regression checks manifest SHA-256 and byte counts, package filters,
  stable queue identities across distinct run IDs, and reloaded claim/completion
  records with their complete events and notes. Review updates are saved to a
  separate handoff so the original run's manifest remains valid.

The API tests additionally exercise malformed envelopes, ownership combinations,
timestamps, event fields, independent duplicate item/replay identities, and writer
rejection without replacing an existing artifact. The runtime implementation now
rejects audit timestamps outside the ordered item lifetime and rejects reuse of
an output directory containing saved review progress. The added tests first failed
against the previous implementation (three chronology cases and two replay cases).

Black's concurrent execution stalled in this sandbox. All 331 Python files were
checked successfully using individual Black invocations with a writable cache;
the required repository-wide command then passed using that verified cache.
All pytest invocations used `-m "not slow"`; `-o addopts=` isolates these acceptance
checks from the unrelated repository-wide coverage threshold.

Unchanged smoke test SHA-256:
`34e2cec3480ed5c1f2583831175212bd6b1b9a03d5afdb3fe18a3c3a1b6d7c2e`.
