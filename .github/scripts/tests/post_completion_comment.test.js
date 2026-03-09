'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');

const {
  buildCompletionComment,
  extractSection,
  postCompletionComment,
} = require('../post_completion_comment.js');

test('buildCompletionComment includes disposition from metadata', () => {
  const body = buildCompletionComment([], [], {
    disposition: '### Rationale\nNo follow-up fix required.',
  });

  assert.match(body, /## Disposition/);
  assert.match(body, /### Rationale/);
  assert.match(body, /No follow-up fix required\./);
});

test('buildCompletionComment appends verify:compare output URL when provided', () => {
  const url = 'https://github.com/example/repo/actions/runs/123456';
  const body = buildCompletionComment([], [], {
    verifyCompareUrl: url,
  });

  assert.match(body, /## Disposition/);
  assert.match(body, /### verify:compare Outcome/);
  assert.match(body, /Disposition note: \[Disposition\]\(#disposition\)/);
  assert.match(body, new RegExp(`- verify:compare output: ${url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`));
  assert.match(body, new RegExp(`- Verification evidence: ${url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`));
});

test('extractSection reads Disposition block without trailing sections', () => {
  const content = [
    '## Tasks',
    '- [x] Done',
    '',
    '## Disposition',
    '### Rationale',
    'Concerns are not warranted.',
    '',
    '## Other',
    'Tail',
  ].join('\n');

  const section = extractSection(content, 'Disposition');
  assert.equal(section, '### Rationale\nConcerns are not warranted.');
});

test('postCompletionComment posts comment when only verify_compare_url is present', async () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'completion-comment-'));
  const promptPath = path.join(tmpDir, 'prompt.md');
  fs.writeFileSync(promptPath, '## Tasks\n- [ ] Pending task\n', 'utf8');

  const comments = [];
  const github = {
    __testMock: true,
    rest: {
      issues: {
        listComments: async () => ({ data: [] }),
        createComment: async ({ body }) => {
          comments.push(body);
          return { data: { id: 99 } };
        },
      },
    },
  };

  const result = await postCompletionComment({
    github,
    context: { repo: { owner: 'acme', repo: 'inv-man' } },
    core: { info() {}, warning() {}, debug() {} },
    inputs: {
      pr_number: 57,
      prompt_file: promptPath,
      verify_compare_url: 'https://github.com/acme/inv-man/actions/runs/42',
    },
  });

  assert.equal(result.posted, true);
  assert.equal(comments.length, 1);
  assert.match(comments[0], /## Disposition/);
  assert.match(comments[0], /verify:compare output: https:\/\/github\.com\/acme\/inv-man\/actions\/runs\/42/);
  assert.match(comments[0], /### verify:compare Outcome/);
  assert.match(comments[0], /Disposition note: \[Disposition\]\(#disposition\)/);
});
