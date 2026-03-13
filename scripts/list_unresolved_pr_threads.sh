#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-stranske/Inv-Man-Intake}"
PR_NUMBER="${1:-76}"
OWNER="${REPO%/*}"
NAME="${REPO#*/}"

query='query($owner:String!, $name:String!, $number:Int!){ repository(owner:$owner, name:$name){ pullRequest(number:$number){ reviewThreads(first:100){ nodes { id isResolved comments(first:1){ nodes { path line url body author{login} } } } } } } }'

output="$(gh api graphql -f owner="$OWNER" -f name="$NAME" -F number="$PR_NUMBER" -f query="$query")"

echo "repo: $REPO"
echo "pr: #$PR_NUMBER"
echo
echo -e "thread_id\tpath\tline\tauthor\tcomment_url"
printf '%s\n' "$output" \
  | jq -r '.data.repository.pullRequest.reviewThreads.nodes[]
      | select(.isResolved == false)
      | [
          .id,
          (.comments.nodes[0].path // "-"),
          ((.comments.nodes[0].line // "-")|tostring),
          (.comments.nodes[0].author.login // "-"),
          (.comments.nodes[0].url // "-")
        ]
      | @tsv'

count="$(
  printf '%s\n' "$output" \
    | jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length'
)"
echo
echo "unresolved_threads_count: $count"
