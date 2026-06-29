# PR #74 Unresolved Review Threads

Source issue: #142
Source PR: #74

## Status

- Blocked in this runner: live GitHub API/`gh` access was unavailable when this note was written.
- The unresolved-thread listing tool is `scripts/list_unresolved_pr_threads.sh`, covered by
  `tests/test_list_unresolved_pr_threads.py`. (An earlier draft of this doc referenced a
  `scripts/list_unresolved_review_threads.py` that was never committed; the shell script is the
  real tool — see #698.)

## Identification Command

Run this from an environment with valid `GH_TOKEN`/`gh` auth:

```bash
REPO=stranske/Inv-Man-Intake ./scripts/list_unresolved_pr_threads.sh 74
```

The output is a tab-separated table with one row per unresolved thread:
`thread_id`, `path`, `line`, `author`, `comment_url`.
