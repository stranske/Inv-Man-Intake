'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { buildTaskAppendix } = require('../keepalive_loop.js');

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

