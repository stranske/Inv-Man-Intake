'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  REVIEW_THREAD_AUDIT_MARKER,
  REVIEW_THREAD_DISPOSITION_MARKER,
  extractUnresolvedReviewThreads,
  buildReviewThreadChecklistComment,
  findExistingAuditComment,
  parseDispositionRepliesInput,
  buildDispositionReplyBody,
  hasDispositionReply,
  postReviewThreadChecklistComment,
  postReviewThreadDispositionReplies,
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

test('parseDispositionRepliesInput accepts JSON arrays and rejects invalid input', () => {
  const parsed = parseDispositionRepliesInput(
    JSON.stringify([{ thread_id: 'T1', disposition: 'fix', fix_reference: 'https://github.com/org/repo/pull/71' }]),
  );
  assert.equal(parsed.length, 1);
  assert.equal(parseDispositionRepliesInput('nope').length, 0);
  assert.equal(parseDispositionRepliesInput(null).length, 0);
});

test('buildDispositionReplyBody enforces required fields for fix and not-warranted dispositions', () => {
  const fixBody = buildDispositionReplyBody({
    disposition: 'fix',
    fix_reference: 'https://github.com/org/repo/pull/71',
  });
  assert.match(fixBody, new RegExp(REVIEW_THREAD_DISPOSITION_MARKER));
  assert.match(fixBody, /Follow-up fix reference: https:\/\/github\.com\/org\/repo\/pull\/71\./);

  const rationaleBody = buildDispositionReplyBody({
    disposition: 'not-warranted',
    rationale: 'This is expected behavior because validation happens in a downstream gate.',
  });
  assert.match(rationaleBody, /Disposition: not warranted\./);
  assert.match(rationaleBody, /expected behavior/);

  assert.equal(
    buildDispositionReplyBody({ disposition: 'fix' }),
    '',
  );
  assert.equal(
    buildDispositionReplyBody({ disposition: 'not-warranted' }),
    '',
  );
});

test('hasDispositionReply identifies existing disposition marker comments', () => {
  assert.equal(
    hasDispositionReply({
      comments: [{ body: `${REVIEW_THREAD_DISPOSITION_MARKER}\nexisting` }],
    }),
    true,
  );
  assert.equal(hasDispositionReply({ comments: [{ body: 'plain comment' }] }), false);
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

test('postReviewThreadDispositionReplies posts only unresolved threads with matching dispositions', async () => {
  const graphqlCalls = [];
  const github = {
    __testMock: true,
    graphql: async (query, variables) => {
      if (query.includes('query UnresolvedReviewThreads')) {
        return {
          repository: {
            pullRequest: {
              reviewThreads: {
                pageInfo: { hasNextPage: false, endCursor: null },
                nodes: [
                  {
                    id: 'T1',
                    isResolved: false,
                    comments: {
                      nodes: [
                        {
                          id: 'C1',
                          url: 'https://github.com/org/repo/pull/70#discussion_r1',
                          path: 'src/a.py',
                          line: 12,
                          body: 'initial comment',
                        },
                      ],
                    },
                  },
                  {
                    id: 'T2',
                    isResolved: false,
                    comments: {
                      nodes: [
                        {
                          id: 'C2',
                          url: 'https://github.com/org/repo/pull/70#discussion_r2',
                          path: 'src/b.py',
                          line: 18,
                          body: `${REVIEW_THREAD_DISPOSITION_MARKER}\nexisting disposition`,
                        },
                      ],
                    },
                  },
                ],
              },
            },
          },
        };
      }
      graphqlCalls.push({ query, variables });
      return { addPullRequestReviewThreadReply: { comment: { id: 'R1', url: 'https://example.com/reply' } } };
    },
  };

  const result = await postReviewThreadDispositionReplies({
    github,
    context: { repo: { owner: 'org', repo: 'repo' } },
    core: { info() {}, warning() {}, debug() {} },
    inputs: {
      pr_number: 70,
      thread_replies: JSON.stringify([
        {
          thread_id: 'T1',
          disposition: 'fix',
          fix_reference: 'https://github.com/org/repo/pull/71',
        },
        {
          thread_id: 'T2',
          disposition: 'not-warranted',
          rationale: 'No change is warranted because this path is intentionally read-only.',
        },
      ]),
    },
  });

  assert.equal(result.posted, true);
  assert.equal(result.postedCount, 1);
  assert.equal(result.unresolvedCount, 2);
  assert.equal(result.skippedAlreadyDispositioned, 1);
  assert.equal(graphqlCalls.length, 1);
  assert.equal(graphqlCalls[0].variables.threadId, 'T1');
  assert.match(graphqlCalls[0].variables.body, /Follow-up fix reference: https:\/\/github\.com\/org\/repo\/pull\/71\./);
});
