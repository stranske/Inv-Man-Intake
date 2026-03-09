# PR #80 Unresolved Review Threads

Source issue: #39  
Source PR: #80  
Follow-up issue: #125

## Thread Inventory

The four unresolved threads were detected by the completion audit, but this run environment cannot resolve `github.com` / `api.github.com`, so direct thread URLs could not be queried live.

| Thread Identifier | Thread URL | Notes |
| --- | --- | --- |
| `pending-thread-1` | pending-fetch | Requires GitHub API/thread scrape in a network-enabled run. |
| `pending-thread-2` | pending-fetch | Requires GitHub API/thread scrape in a network-enabled run. |
| `pending-thread-3` | pending-fetch | Requires GitHub API/thread scrape in a network-enabled run. |
| `pending-thread-4` | pending-fetch | Requires GitHub API/thread scrape in a network-enabled run. |

## Retrieval Command (when network is available)

```bash
env -u GH_TOKEN gh api graphql -f query='query($owner:String!, $repo:String!, $number:Int!) { repository(owner:$owner, name:$repo) { pullRequest(number:$number) { reviewThreads(first:100) { nodes { id isResolved comments(first:1) { nodes { databaseId url } } } } } } }' -f owner='stranske' -f repo='Inv-Man-Intake' -F number=80 > /tmp/pr80-review-threads.json
python scripts/unresolved_thread_inventory.py /tmp/pr80-review-threads.json
```

## Next Update Needed

- Replace `pending-thread-*` rows with the 4 concrete `discussion_r...` links produced by `scripts/unresolved_thread_inventory.py`.
- Continue with classification and final disposition once the thread list is populated.
