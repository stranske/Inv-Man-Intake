#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-stranske/Inv-Man-Intake}"
PR_NUMBER="${1:-76}"
OWNER="${REPO%/*}"
NAME="${REPO#*/}"
DISPOSITION_DOC="${DISPOSITION_DOC:-docs/pr-76-thread-disposition.md}"

query="$(cat <<'EOF'
query($owner:String!, $name:String!, $number:Int!){
  repository(owner:$owner, name:$name){
    pullRequest(number:$number){
      reviewThreads(first:100){
        nodes {
          id
          isResolved
          comments(first:1){
            nodes {
              path
              line
              url
              author { login }
            }
          }
        }
      }
    }
  }
}
EOF
)"

print_header() {
  echo "repo: $REPO"
  echo "pr: #$PR_NUMBER"
  echo
  printf 'thread_id\tpath\tline\tauthor\tcomment_url\n'
}

print_from_api() {
  local output="$1"
  print_header
  printf '%s\n' "$output" \
    | jq -r '.data.repository.pullRequest.reviewThreads.nodes[]
        | select(.isResolved == false)
        | [
            .id,
            (.comments.nodes[0].path // "-"),
            ((.comments.nodes[0].line // "-") | tostring),
            (.comments.nodes[0].author.login // "-"),
            (.comments.nodes[0].url // "-")
          ]
        | @tsv'

  local count
  count="$(
    printf '%s\n' "$output" \
      | jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length'
  )"
  echo
  echo "unresolved_threads_count: $count"
}

print_from_doc() {
  if [[ ! -f "$DISPOSITION_DOC" ]]; then
    echo "error: GitHub API request failed and fallback doc not found: $DISPOSITION_DOC" >&2
    return 1
  fi

  print_header

  awk -F'|' '
    BEGIN {
      count = 0
    }
    /^\| [0-9]+ / {
      thread_id = trim($3)
      location = trim($4)
      print thread_id "\t" location "\t-\tlocal-doc\t-"
      count++
    }
    END {
      printf "\nunresolved_threads_count: %d\n", count
    }
    function trim(value) {
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]]+$/, "", value)
      return value
    }
  ' "$DISPOSITION_DOC"
}

if output="$(gh api graphql -f owner="$OWNER" -f name="$NAME" -F number="$PR_NUMBER" -f query="$query" 2>/dev/null)"; then
  print_from_api "$output"
else
  echo "warning: gh api graphql failed; using fallback data from $DISPOSITION_DOC" >&2
  print_from_doc
fi
