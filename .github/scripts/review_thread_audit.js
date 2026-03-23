'use strict';

const { ensureRateLimitWrapped } = require('./github-rate-limited-wrapper.js');

const REVIEW_THREAD_AUDIT_MARKER = '<!-- agent-review-thread-audit -->';
const REVIEW_THREAD_DISPOSITION_MARKER = '<!-- agent-review-thread-disposition -->';

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
          comments(first: 50) {
            nodes {
              id
              url
              path
              line
              originalLine
              body
            }
          }
        }
      }
    }
  }
}
`;

const ADD_REVIEW_THREAD_REPLY_MUTATION = `
mutation AddReviewThreadReply($threadId: ID!, $body: String!) {
  addPullRequestReviewThreadReply(input: { pullRequestReviewThreadId: $threadId, body: $body }) {
    comment {
      id
      url
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
      const comments =
        thread?.comments?.nodes && Array.isArray(thread.comments.nodes) ? thread.comments.nodes : [];
      return {
        id: String(thread.id || ''),
        url: comment?.url || '',
        location: toThreadLocation(comment),
        isOutdated: Boolean(thread.isOutdated),
        comments: comments.map((item) => ({
          id: String(item?.id || ''),
          url: String(item?.url || ''),
          body: String(item?.body || ''),
        })),
      };
    });
}

function parseDispositionRepliesInput(rawInput) {
  if (!rawInput) {
    return [];
  }
  if (Array.isArray(rawInput)) {
    return rawInput;
  }
  if (typeof rawInput !== 'string') {
    return [];
  }
  try {
    const parsed = JSON.parse(rawInput);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function resolveDispositionEntry(thread, entries) {
  if (!thread || !Array.isArray(entries) || entries.length === 0) {
    return null;
  }
  const threadDiscussionId = extractDiscussionId(thread.url);
  return (
    entries.find((entry) => String(entry?.thread_id || '') === thread.id) ||
    entries.find((entry) => String(entry?.thread_url || '') === thread.url) ||
    (threadDiscussionId &&
      entries.find(
        (entry) =>
          String(entry?.thread_discussion_id || '') === threadDiscussionId ||
          extractDiscussionId(entry?.thread_url) === threadDiscussionId,
      )) ||
    null
  );
}

function extractDiscussionId(value) {
  const match = String(value || '').match(/#(discussion_r\d+)/i);
  return match ? match[1].toLowerCase() : '';
}

function hasCompleteSentence(text) {
  const value = String(text || '').trim();
  if (!value) {
    return false;
  }
  const sentences = value.match(/[^.!?]+[.!?]/g) || [];
  return sentences.some((sentence) => sentence.trim().split(/\s+/).filter(Boolean).length >= 3);
}

function isFollowUpFixReference(value) {
  const candidate = String(value || '').trim();
  if (!candidate) {
    return false;
  }
  return /^https:\/\/github\.com\/[^/\s]+\/[^/\s]+\/(pull\/\d+|commit\/[0-9a-f]{7,40})(?:[^\s]*)?$/i.test(
    candidate,
  );
}

function buildDispositionReplyBody(entry) {
  const disposition = String(entry?.disposition || '').trim().toLowerCase();
  const fixRef = String(entry?.fix_reference || '').trim();
  const rationale = String(entry?.rationale || '').trim();
  const note = String(entry?.note || '').trim();
  const sourcePr = Number(entry?.source_pr || entry?.sourcePr || 0);
  const sourceIssue = Number(entry?.source_issue || entry?.sourceIssue || 0);
  const lines = [REVIEW_THREAD_DISPOSITION_MARKER];

  if (sourcePr > 0 || sourceIssue > 0) {
    const refs = [];
    if (sourcePr > 0) {
      refs.push(`PR #${sourcePr}`);
    }
    if (sourceIssue > 0) {
      refs.push(`issue #${sourceIssue}`);
    }
    lines.push(`Context: ${refs.join(' and ')}.`);
  }

  if (disposition === 'fix' || disposition === 'warranted-fix') {
    if (!isFollowUpFixReference(fixRef)) {
      return '';
    }
    lines.push(`Follow-up fix reference: ${fixRef}.`);
    if (note) {
      lines.push(note);
    }
    return lines.join('\n');
  }

  if (disposition === 'not-warranted') {
    if (!hasCompleteSentence(rationale)) {
      return '';
    }
    lines.push(`Disposition: not warranted. ${rationale}`);
    if (note) {
      lines.push(note);
    }
    return lines.join('\n');
  }

  return '';
}

function hasDispositionReply(thread) {
  if (!thread || !Array.isArray(thread.comments)) {
    return false;
  }
  return thread.comments.some((comment) =>
    String(comment?.body || '').includes(REVIEW_THREAD_DISPOSITION_MARKER),
  );
}

function parseBooleanInput(rawValue) {
  if (typeof rawValue === 'boolean') {
    return rawValue;
  }
  if (typeof rawValue === 'number') {
    return rawValue !== 0;
  }
  const normalized = String(rawValue || '').trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return ['1', 'true', 'yes', 'on'].includes(normalized);
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

async function postReviewThreadDispositionReplies({
  github: rawGithub,
  context,
  core,
  inputs,
}) {
  const github = await ensureRateLimitWrapped({ github: rawGithub, core, env: process.env });
  const prNumber = Number(inputs.pr_number || inputs.prNumber || 0);
  const replyEntries = parseDispositionRepliesInput(inputs.thread_replies || inputs.threadReplies);
  const requireCompleteReplies = parseBooleanInput(
    inputs.require_complete_replies ?? inputs.requireCompleteReplies,
  );

  if (!prNumber || prNumber <= 0) {
    return { posted: false, reason: 'missing-pr-number' };
  }
  if (replyEntries.length === 0) {
    return { posted: false, reason: 'missing-thread-replies' };
  }

  const { owner, repo } = context.repo;
  const unresolvedThreads = await fetchAllUnresolvedReviewThreads({
    github,
    owner,
    repo,
    prNumber,
  });

  let postedCount = 0;
  let skippedMissing = 0;
  let skippedAlreadyDispositioned = 0;
  const missingThreadIds = [];

  for (const thread of unresolvedThreads) {
    const entry = resolveDispositionEntry(thread, replyEntries);
    if (!entry) {
      skippedMissing += 1;
      missingThreadIds.push(thread.id || thread.url || 'unknown-thread');
      continue;
    }
    if (hasDispositionReply(thread)) {
      skippedAlreadyDispositioned += 1;
      continue;
    }
    const body = buildDispositionReplyBody(entry);
    if (!body) {
      skippedMissing += 1;
      missingThreadIds.push(thread.id || thread.url || 'unknown-thread');
      continue;
    }

    await github.graphql(ADD_REVIEW_THREAD_REPLY_MUTATION, {
      threadId: thread.id,
      body,
    });
    postedCount += 1;
  }

  core?.info?.(
    `Posted review-thread dispositions: posted=${postedCount}, missing=${skippedMissing}, already=${skippedAlreadyDispositioned}`,
  );

  if (requireCompleteReplies && missingThreadIds.length > 0) {
    throw new Error(
      `Missing disposition replies for unresolved review threads: ${missingThreadIds.join(', ')}`,
    );
  }

  return {
    posted: postedCount > 0,
    postedCount,
    unresolvedCount: unresolvedThreads.length,
    skippedMissing,
    skippedAlreadyDispositioned,
    missingThreadIds,
  };
}

module.exports = {
  REVIEW_THREAD_AUDIT_MARKER,
  REVIEW_THREAD_DISPOSITION_MARKER,
  REVIEW_THREADS_QUERY,
  ADD_REVIEW_THREAD_REPLY_MUTATION,
  extractUnresolvedReviewThreads,
  buildReviewThreadChecklistComment,
  findExistingAuditComment,
  parseDispositionRepliesInput,
  parseBooleanInput,
  resolveDispositionEntry,
  extractDiscussionId,
  hasCompleteSentence,
  isFollowUpFixReference,
  buildDispositionReplyBody,
  hasDispositionReply,
  fetchAllUnresolvedReviewThreads,
  postReviewThreadChecklistComment,
  postReviewThreadDispositionReplies,
};
