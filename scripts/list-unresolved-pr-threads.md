# How to Find Unresolved Review Threads on a PR

This guide shows how to identify unresolved inline review threads, including for merged pull requests.

## GitHub UI (Merged or Open PR)

Use these steps when the PR is already merged:

1. Open the repository on GitHub and go to **Pull requests**.
2. Change the PR filter to **Closed** and open the merged PR you want to audit.
3. In that PR, open the **Conversation** tab.
4. Find inline review threads that still show an active **Resolve conversation** button.
5. Open the kebab menu (`...`) on a comment and use **Copy link** to save each unresolved thread URL for tracking.
6. Cross-check in **Files changed** to confirm the exact file/line context for each unresolved thread.
7. If needed, add a follow-up PR link and return to the original thread to mark it resolved after disposition.

Tips:
- For merged PRs, conversation threads remain available on the PR page.
- If you are triaging audit findings, keep a checklist with each unresolved thread URL and current disposition.

## GitHub CLI (`gh`) Examples

Prerequisites:
- Authenticate once: `gh auth login`
- Set repo context: `gh repo set-default <owner>/<repo>`

### 1) Quick list of review comments for a PR

```bash
gh api repos/<owner>/<repo>/pulls/<pr-number>/comments \
  --paginate \
  --jq '.[] | {id, path, line, user: .user.login, created_at, html_url, body}'
```

Use the output URLs to open each comment and determine whether its thread is resolved.

### 2) GraphQL: fetch review threads with `isResolved`

```bash
gh api graphql -f query='\
query($owner:String!, $repo:String!, $number:Int!) {\
  repository(owner:$owner, name:$repo) {\
    pullRequest(number:$number) {\
      reviewThreads(first:100) {\
        nodes {\
          isResolved\
          isOutdated\
          path\
          line\
          comments(first:1) {\
            nodes {\
              url\
              body\
              author { login }\
              createdAt\
            }\
          }\
        }\
      }\
    }\
  }\
}' -f owner='<owner>' -f repo='<repo>' -F number=<pr-number>
```

Filter unresolved threads only:

```bash
gh api graphql -f query='\
query($owner:String!, $repo:String!, $number:Int!) {\
  repository(owner:$owner, name:$repo) {\
    pullRequest(number:$number) {\
      reviewThreads(first:100) {\
        nodes {\
          isResolved\
          path\
          line\
          comments(first:1) { nodes { url body } }\
        }\
      }\
    }\
  }\
}' -f owner='<owner>' -f repo='<repo>' -F number=<pr-number> \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)'
```

## GitHub API (without `gh`)

### REST: list PR review comments

```bash
curl -sS \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/<owner>/<repo>/pulls/<pr-number>/comments?per_page=100"
```

### GraphQL: list unresolved threads directly

```bash
curl -sS https://api.github.com/graphql \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{
  "query": "query($owner:String!, $repo:String!, $number:Int!){ repository(owner:$owner, name:$repo){ pullRequest(number:$number){ reviewThreads(first:100){ nodes{ isResolved path line comments(first:1){ nodes{ url body } } } } } } }",
  "variables": {
    "owner": "<owner>",
    "repo": "<repo>",
    "number": <pr-number>
  }
}
JSON
```

Then select threads where `isResolved` is `false`.

## Suggested Triage Output

When documenting unresolved threads in a local review note, include:
- Thread/comment URL
- Reviewer concern summary
- Proposed disposition (`fix`, `defer`, or `reject`)
- Rationale and next action
