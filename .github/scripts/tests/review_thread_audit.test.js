'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  REVIEW_THREAD_AUDIT_MARKER,
  extractUnresolvedReviewThreads,
  buildReviewThreadChecklistComment,
  findExistingAuditComment,
  postReviewThreadChecklistComment,
} = require('../review_thread_audit.js');

test('extractUnresolvedReviewThreads returns only unresolved threads with direct links', () => {
  const payload = {
    repository: {
      pullRequest: {
        reviewThreads: {
          nodes: [
            {
              id: 'T1',
              isResolved: false,
              comments: {
                nodes: [{ url: 'https://github.com/org/repo/pull/70#discussion_r1', path: 'src/a.py', line: 12 }],
              },
            },
            {
              id: 'T2',
              isResolved: true,
              comments: {
                nodes: [{ url: 'https://github.com/org/repo/pull/70#discussion_r2', path: 'src/b.py', line: 9 }],
              },
            },
          ],
        },
      },
    },
  };

  const unresolved = extractUnresolvedReviewThreads(payload);
  assert.equal(unresolved.length, 1);
  assert.equal(unresolved[0].id, 'T1');
  assert.equal(unresolved[0].url, 'https://github.com/org/repo/pull/70#discussion_r1');
  assert.equal(unresolved[0].location, 'src/a.py:12');
});

test('buildReviewThreadChecklistComment includes checklist entries with direct links', () => {
  const body = buildReviewThreadChecklistComment({
    prNumber: 70,
    sourceIssueNumber: 35,
    unresolvedThreads: [
      { url: 'https://github.com/org/repo/pull/70#discussion_r1', location: 'src/a.py:12' },
      { url: 'https://github.com/org/repo/pull/70#discussion_r2', location: 'src/b.py:8' },
    ],
    generatedAt: '2026-03-09T12:00:00.000Z',
  });

  assert.match(body, /Review Thread Audit Checklist \(PR #70\)/);
  assert.match(body, /Source issue: #35/);
  assert.match(body, /Snapshot unresolved inline review threads: 2/);
  assert.match(body, /- \[ \] Thread 1: \[src\/a\.py:12\]\(https:\/\/github\.com\/org\/repo\/pull\/70#discussion_r1\)/);
  assert.match(body, /- \[ \] Thread 2: \[src\/b\.py:8\]\(https:\/\/github\.com\/org\/repo\/pull\/70#discussion_r2\)/);
});

test('findExistingAuditComment locates marker comment', () => {
  const comment = findExistingAuditComment([
    { id: 1, body: 'irrelevant' },
    { id: 2, body: `${REVIEW_THREAD_AUDIT_MARKER}\nhello` },
  ]);
  assert.equal(comment?.id, 2);
});

test('postReviewThreadChecklistComment creates comment when marker is absent', async () => {
  const created = [];
  const github = {
    __testMock: true,
    graphql: async () => ({
      repository: {
        pullRequest: {
          reviewThreads: {
            pageInfo: { hasNextPage: false, endCursor: null },
            nodes: [
              {
                id: 'T1',
                isResolved: false,
                comments: {
                  nodes: [{ url: 'https://github.com/org/repo/pull/70#discussion_r1', path: 'src/a.py', line: 12 }],
                },
              },
            ],
          },
        },
      },
    }),
    rest: {
      issues: {
        listComments: async () => ({ data: [] }),
        createComment: async ({ body }) => {
          created.push(body);
          return { data: { id: 91 } };
        },
      },
    },
  };

  const result = await postReviewThreadChecklistComment({
    github,
    context: { repo: { owner: 'org', repo: 'repo' } },
    core: { info() {}, warning() {}, debug() {} },
    inputs: { pr_number: 70, source_issue: 35 },
  });

  assert.equal(result.posted, true);
  assert.equal(result.created, true);
  assert.equal(result.unresolvedCount, 1);
  assert.equal(created.length, 1);
  assert.match(created[0], /Thread 1: \[src\/a\.py:12\]\(https:\/\/github\.com\/org\/repo\/pull\/70#discussion_r1\)/);
});
