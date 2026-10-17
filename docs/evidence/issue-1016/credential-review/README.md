# Remote opt-in credential gate review

Review: https://github.com/stranske/Inv-Man-Intake/pull/1025#discussion_r4303235906

The existing parameterized entrypoint test now includes absent and whitespace-only LANGSMITH_API_KEY with both remote opt-in and tracing enabled. Each retains local start/end span events and asserts zero remote client construction and remote events.

Commands used `/opt/anaconda3/bin/python3` in the repository worktree. Full focused command: `python -m pytest tests/observability/test_tracing_toggle.py tests/test_v1_acceptance_smoke.py -q -o addopts=''`: 43 passed. Credential command: `python -m pytest tests/observability/test_tracing_toggle.py -k requires_explicit_remote_opt_in -q -o addopts=''`.

The exact temporary predicate replacement is in 1025-mutation.json. Removing only the credential condition made the two new unchanged cases fail (2 failed, 4 passed). Restoring byte-identical production source made all six controls pass. This test-only review repair changes no production behavior. Base main was merged without rebasing existing native commits; upstream workflow changes are inherited base, not a new source repair.

Published transcript lines remove trailing whitespace only; transcript-hashes.json binds the raw automation capture and readable repository copy.
