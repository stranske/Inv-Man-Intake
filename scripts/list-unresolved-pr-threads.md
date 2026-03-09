# How to Find Unresolved Review Threads on a PR

This guide shows how to identify unresolved inline review threads, including for merged pull requests.

## GitHub UI (Merged or Open PR)

1. Open the repository pull requests page and select the target PR.
2. Click the **Conversation** tab on the PR.
3. Scroll through review comments and look for thread status controls (for example, **Resolve conversation** on unresolved threads).
4. Unresolved threads stay visible as open conversations; resolved threads are collapsed/marked as resolved.
5. To inspect file context, open the **Files changed** tab and use the comment anchors to jump to the matching inline thread.

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
