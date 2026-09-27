# PR #981 deliberate-break evidence disposition

Issue #985 asks for recovery of the deliberate-break transcript required by
source issue #949. This disposition is based only on the durable PR record; it
does not reconstruct or infer historical command output.

## Evidence inspected

- `gh pr view 981 -R stranske/Inv-Man-Intake --json body,comments`
- `gh pr checks 981 -R stranske/Inv-Man-Intake`
- PR source head (`headRefOid`)
  `bbbc56c07340ba2425a1964a83270edff86433a1`
- merge commit (`mergeCommit`) `72eb48061c14b4c635b2654c4bf42bf95deea8de`
- keepalive review-resolution note in
  [PR comment 5790000862](https://github.com/stranske/Inv-Man-Intake/pull/981#issuecomment-5790000862)
- closer exact-head merge adjudication in
  [PR comment 5790195185](https://github.com/stranske/Inv-Man-Intake/pull/981#issuecomment-5790195185)
- post-merge provider comparison in
  [PR comment 5790257215](https://github.com/stranske/Inv-Man-Intake/pull/981#issuecomment-5790257215)

## Deliberate-break result

The PR body and linked issue #949 require a deliberate-break gate for
`tests/emit/test_evidence_object_emitter.py::test_run_evidence_refs_are_evidence_ids`:
revert `src/inv_man_intake/run.py:113-118` to emit page-pointer strings so the
named test **must FAIL**, then restore evidence-ID emission.

The keepalive resolution comment summarizes a deliberate regression on adjacent
validation paths (manifest `None`, malformed reference typing) and states that
two targeted tests failed and then passed after restoration. It does not preserve
the actual pytest console output from reverting `run.py:113-118` for the named
acceptance test. The closer adjudication records that a deliberate-break
red/green proof exists in prose but likewise does not quote fail/restored-pass
output for that gate. The durable PR body and comments therefore do not preserve
the required page-pointer revert transcript. Those historical outputs cannot be
recovered from PR #981 and must not be recreated after the fact and represented
as the original transcript.

## Final check state

The live `gh pr checks` read on 2026-09-27 reports successful final product and
Gate coverage, including:

- `Gate / gate`, `gate`, and `gate-summary`
- Python 3.12 and 3.13 matrix (`lint-ruff`, `lint-format`, `typecheck-mypy`)
- `web-smoke` and backplane conformance where applicable
- entity, extraction-golden, foundation-fixture, NL-SQL, one-PDF pilot,
  PostgreSQL, replay, and SLA checks where in scope for the merged head
- Health 45 Agents Guard
- post-merge verifier provider comparison (OpenAI PASS; Anthropic CONCERNS tied
  to credential availability, not implementation)

The exact-head merge adjudication records zero active non-outdated review threads
and substitute advisory evidence where CodeRabbit was capacity-limited. No
failing final check is reported on the merged PR record.

## Disposition

The final check state and restored implementation are durable, but the required
page-pointer revert red/green transcript for the named acceptance test is not.
Issue #985 is the linked evidence follow-up that records this unrecoverable gap
without fabricating historical output.
