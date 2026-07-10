# UX Review Policy

The repository-owned UX review policy lives in `config/ux_review_policy.json`.
`inv_man_intake.ux_review.evaluate_ux_review()` applies that policy and returns a
structured score, pass/block decision, severity-4 categories, and policy-review
status.

## Current Policy

The `ux-review-policy/v1` defaults are:

- usability-panel score: 50%
- adversarial-review score: 30%
- owner-calibration score: 20%
- passing score: at least 7.0 out of 10
- any configured severity-4 finding: hard block regardless of score

Severity 4 is reserved for security or privacy exposure, data loss or
corruption, an unusable core workflow with no reasonable workaround, or an
accessibility failure that prevents a core workflow.

## Performance And Tuning

These defaults are policy choices, not permanent facts. Raising the pass
threshold or increasing adversarial weight makes review stricter and may catch
more regressions, but can also increase false positives, review effort, and time
to release. Lowering them can improve throughput while increasing the chance
that material UX defects pass. Changes can also affect observed product
performance because teams will optimize toward the measured dimensions.

Change the versioned JSON policy instead of embedding alternate thresholds in
callers. A policy change requires focused tests plus a review note comparing:

- pass and block rates before and after the proposed change
- severity-4 incidence by category
- owner overrides and their reasons
- downstream regressions found after a PASS
- review runtime and completion rate

## Review Cadence

Review `ux-review-policy/v1` by **2026-10-15**, or earlier after 20 completed UX
reviews or a material workflow/model change. A due review does not silently
change scoring. It requires an evidence-backed decision to retain or revise the
policy, a new effective date, and a later `review_by` date.

Callers should pass their completed-review count and evaluation date to
`evaluate_ux_review()`. The returned `policy_review_due` flag lets automation
surface the review without changing the current PASS/FAIL result.
