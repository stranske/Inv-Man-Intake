'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { autoReconcileTasks, buildTaskAppendix } = require('../keepalive_loop.js');

test('suggested next task skips previously attempted task and falls through to acceptance criteria', () => {
  const sections = {
    scope: 'Scope text',
    tasks: '- [ ] Re-litigating checklist formatting.',
    acceptance: [
      '- [ ] Locate the verify:compare non-PASS output from PR #57 and identify the specific concerns raised',
      '- [ ] Create a `## Disposition` section in the PR #57 completion audit record',
    ].join('\n'),
  };

  const appendix = buildTaskAppendix(
    sections,
    { checked: 0, total: 3, unchecked: 3 },
    {
      attempted_tasks: [{ task: 'Re-litigating checklist formatting.' }],
    },
  );

  assert.match(appendix, /### Suggested Next Task/);
  assert.match(
    appendix,
    /- Locate the verify:compare non-PASS output from PR #57 and identify the specific concerns raised/,
  );
  assert.doesNotMatch(appendix, /### Suggested Next Task\n- Re-litigating checklist formatting\./);
});

test('autoReconcileTasks checks markdown issue-link task when llm emits plain issue ref', async () => {
  const originalBody = [
    '## Tasks',
    '- [ ] [#57](https://github.com/stranske/Inv-Man-Intake/issues/57)',
  ].join('\n');

  let updatedBody = '';
  const github = {
    __testMock: true,
    rest: {
      pulls: {
        get: async () => ({
          data: {
            body: originalBody,
            title: 'Follow-up for #57',
            head: { ref: 'codex/issue-57' },
          },
        }),
        listFiles: async () => ({ data: [] }),
        update: async ({ body }) => {
          updatedBody = body;
          return { data: {} };
        },
      },
      repos: {
        compareCommits: async () => ({ data: { commits: [] } }),
      },
    },
  };

  const result = await autoReconcileTasks({
    github,
    context: { repo: { owner: 'stranske', repo: 'Inv-Man-Intake' } },
    prNumber: 57,
    baseSha: 'abc123',
    headSha: 'def456',
    llmCompletedTasks: ['#57'],
    core: { info() {}, warning() {}, debug() {} },
  });

  assert.equal(result.updated, true);
  assert.equal(result.tasksChecked, 1);
  assert.match(updatedBody, /- \[x\] \[#57\]\(https:\/\/github\.com\/stranske\/Inv-Man-Intake\/issues\/57\)/);
});
