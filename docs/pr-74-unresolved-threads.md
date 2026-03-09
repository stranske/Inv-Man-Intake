# PR #74 Unresolved Review Threads

Source issue: #142  
Source PR: #74

## Status

- Blocked in this runner: live GitHub API/`gh` access is unavailable.
- Added local extraction tooling in `scripts/list_unresolved_review_threads.py` with tests in
  `tests/test_list_unresolved_review_threads.py`.

## Identification Command

Run this from an environment with valid `GH_TOKEN`:

```bash
python scripts/list_unresolved_review_threads.py --owner stranske --repo Inv-Man-Intake --pr 74 --format checklist
```

The checklist output documents each unresolved thread with:
- Thread URL
- File/line location
- Quoted comment text (blockquoted)

For offline verification with a saved GraphQL payload:

```bash
python scripts/list_unresolved_review_threads.py --pr 74 --input-json /path/to/pr74-review-threads.json --format checklist
```
