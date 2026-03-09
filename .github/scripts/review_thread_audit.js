'use strict';

const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const REVIEW_THREAD_AUDIT_MARKER = '<!-- agent-review-thread-audit -->';

const REVIEW_THREADS_QUERY = `
query UnresolvedReviewThreads($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      reviewThreads(first: 50, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          isResolved
          isOutdated
          comments(first: 1) {
            nodes {
              url
              path
              line
              originalLine
            }
          }
        }
      }
    }
  }
}
`;

function toThreadLocation(comment) {
  if (!comment) {
    return 'unknown location';
  }
  const path = String(comment.path || '').trim();
  const line = comment.line ?? comment.originalLine ?? null;
  if (path && Number.isInteger(line)) {
    return `${path}:${line}`;
  }
  if (path) {
    return path;
  }
  return 'unknown location';
}

function extractUnresolvedReviewThreads(payload) {
  const nodes =
    payload?.repository?.pullRequest?.reviewThreads?.nodes &&
    Array.isArray(payload.repository.pullRequest.reviewThreads.nodes)
      ? payload.repository.pullRequest.reviewThreads.nodes
      : [];

  return nodes
    .filter((thread) => thread && thread.isResolved !== true)
    .map((thread) => {
      const comment = thread?.comments?.nodes?.[0] || null;
      return {
        id: String(thread.id || ''),
        url: comment?.url || '',
        location: toThreadLocation(comment),
        isOutdated: Boolean(thread.isOutdated),
      };
    });
}

function buildReviewThreadChecklistComment({ prNumber, sourceIssueNumber, unresolvedThreads, generatedAt }) {
  const threads = Array.isArray(unresolvedThreads) ? unresolvedThreads : [];
  const lines = [
    REVIEW_THREAD_AUDIT_MARKER,
    `## Review Thread Audit Checklist (PR #${prNumber})`,
    '',
    `Source issue: #${sourceIssueNumber}`,
    `Snapshot unresolved inline review threads: ${threads.length}`,
    `Generated at: ${generatedAt || new Date().toISOString()}`,
    '',
    '### Unresolved Threads',
  ];

  if (threads.length === 0) {
    lines.push('- [x] No unresolved inline review threads remain.');
  } else {
    for (const [index, thread] of threads.entries()) {
      const label = thread.location || `thread-${index + 1}`;
      const link = thread.url || '(missing direct link)';
      lines.push(`- [ ] Thread ${index + 1}: [${label}](${link})`);
    }
  }

  lines.push('');
  lines.push('### Status');
  lines.push('- [ ] Each thread has a disposition reply (fix link or not-warranted rationale).');
  lines.push('- [ ] Unresolved thread count confirmed as 0.');
  return lines.join('\n');
}

function findExistingAuditComment(comments) {
  if (!Array.isArray(comments)) {
    return null;
  }
  return comments.find((comment) => String(comment?.body || '').includes(REVIEW_THREAD_AUDIT_MARKER)) || null;
}

async function fetchAllUnresolvedReviewThreads({ github, owner, repo, prNumber }) {
  let cursor = null;
  const allThreads = [];

  do {
    const data = await github.graphql(REVIEW_THREADS_QUERY, {
      owner,
      repo,
      number: prNumber,
      cursor,
    });
    const reviewThreads = data?.repository?.pullRequest?.reviewThreads;
    const unresolved = extractUnresolvedReviewThreads(data);
    allThreads.push(...unresolved);
    const pageInfo = reviewThreads?.pageInfo || { hasNextPage: false, endCursor: null };
    cursor = pageInfo.hasNextPage ? pageInfo.endCursor : null;
  } while (cursor);

  return allThreads;
}

async function postReviewThreadChecklistComment({
  github: rawGithub,
  context,
  core,
  inputs,
}) {
  const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  const prNumber = Number(inputs.pr_number || inputs.prNumber || 0);
  const sourceIssueNumber = Number(inputs.source_issue || inputs.sourceIssue || 0);

  if (!prNumber || prNumber <= 0) {
    return { posted: false, reason: 'missing-pr-number' };
  }
  if (!sourceIssueNumber || sourceIssueNumber <= 0) {
    return { posted: false, reason: 'missing-source-issue' };
  }

  const { owner, repo } = context.repo;
  const unresolvedThreads = await fetchAllUnresolvedReviewThreads({
    github,
    owner,
    repo,
    prNumber,
  });

  const body = buildReviewThreadChecklistComment({
    prNumber,
    sourceIssueNumber,
    unresolvedThreads,
  });

  const { data: comments } = await github.rest.issues.listComments({
    owner,
    repo,
    issue_number: prNumber,
    per_page: 100,
  });
  const existing = findExistingAuditComment(comments);

  if (existing) {
    await github.rest.issues.updateComment({
      owner,
      repo,
      comment_id: existing.id,
      body,
    });
    core?.info?.(`Updated review-thread audit checklist comment (id=${existing.id})`);
    return {
      posted: true,
      updated: true,
      commentId: existing.id,
      unresolvedCount: unresolvedThreads.length,
    };
  }

  const { data: created } = await github.rest.issues.createComment({
    owner,
    repo,
    issue_number: prNumber,
    body,
  });
  core?.info?.(`Created review-thread audit checklist comment (id=${created.id})`);
  return {
    posted: true,
    created: true,
    commentId: created.id,
    unresolvedCount: unresolvedThreads.length,
  };
}

module.exports = {
  REVIEW_THREAD_AUDIT_MARKER,
  REVIEW_THREADS_QUERY,
  extractUnresolvedReviewThreads,
  buildReviewThreadChecklistComment,
  findExistingAuditComment,
  fetchAllUnresolvedReviewThreads,
  postReviewThreadChecklistComment,
};
