# UX Review Log — Inv-Man-Intake

Diff-anchored record of UX Review (`/ux-review`) passes. Each entry's commit SHA anchors the next
review's git-diff focus. Detailed artifacts live in `Orchestrator/ux_reviews/`.

## 2026-06-22 — Scoring/intake demo (`app/streamlit_app.py`), full coverage — commit `b91b4a9` — overall 3.0/10 (gate FAIL)

- **Coverage:** main scoring view ✓ (Final score + Explainability + Analyst queue); bundle selector ✓ (default fixture). **NOT driven:** the other fixture bundles; the stlite build (`app/index.html`) not separately served.
- **Scores:** wired 7.0 / usability 5.5 / help_clarity 5.5 / workflow 5.0 (2 sev-4 blockers + 2 sev-3).
- **Headline:** the scoring + Explainability table are strong (clear weights + rationales), but the **Analyst queue — the analyst's actual workflow — is a non-actionable raw JSON dump**, so the workflow dead-ends after scoring.
- **Findings → filed:**
  - Analyst queue non-actionable: raw `st.write({...item_id...})` (`app/streamlit_app.py:178`), opaque id, no description, no actions → **#629** (workflow sev4).
  - Dev details leak into the UI: trace-sink `st.success` banner (`:179`) + raw fixture filenames in the selector (`:171`) → **#630**.
- **Next focus:** after #629/#630, re-check; drive the other fixture bundles + the stlite build (`app/index.html`).

## 2026-06-23 — Re-test after #629/#644 — commit `05b5166` — overall 3.0/10 (gate FAIL)

- **Diff since `b91b4a9`:** `app/streamlit_app.py` +92 (analyst-queue rebuild); `#644` vendored an offline stlite runtime (`app/vendor/`, `app/pypi/`) + repointed `app/index.html`.
- **Coverage (prior gaps now driven):** shipped offline stlite build (`app/index.html`) ✓ DRIVEN in headless Chromium served locally, no network — **FAILS to boot**; server-side scoring view ✓; Explainability ✓ (now has weight + rationale columns); Analyst queue card ✓; both fixture bundles ✓ (pptx function-verified — closes prior gap); analyst actions function-verified (Accept→Accepted persists). **Not driven:** Escalate/Needs-info DOM outcomes, empty-state when all actioned, narrow-viewport, edge-threshold fixtures (→ next focus).
- **Scores:** wired 3.0 / usability 4.5 / help_clarity 4.5 / workflow 5.0; all dimensions consensus-flagged; adversarial critic refuted nothing. Panel: claude 3/4/4/4 · codex 3/4/5/5 · cursor 4/5/5/6 · vibe 3/5/3/5.
- **Headline (score held at 3.0, reason changed):** #629's analyst-queue dead-end is **resolved** (readable card + persisted Accept/Escalate/Needs-info), but driving the previously-skipped shipped artifact surfaced a **deeper sev-4 blocker**: the offline stlite build does not boot. Full-coverage discipline caught what a happy-path re-score would have missed.
- **Findings → disposition:**
  - Analyst queue (issue 629): **FIXED** — verified live + function-level (`build_analyst_queue_card`/`render_analyst_queue`, `:179`/`:224`).
  - Offline build won't boot (issue 639, deployment-hardening; #644 was an incomplete attempt, correctly reopened): (a) worker-relative `pyodideUrl` 404 (verified fix: absolute `new URL(...).href`); (b) vendored Pyodide is core-only — micropip + scientific stack not vendored; (c) committed live-verification artifact is a stale 2026-06-02 CDN run (fake-green). Re-test evidence + verified fix added as a comment.
  - Dev-detail leak (issue 630): **still present** — trace-sink banner `:270` + raw-filename selector `:262`; panel corroborated the raw filename. Corroboration commented.
- **Next focus:** after issue 639 lands, re-drive `app/index.html` offline (expect zero CDN requests + score `0.7809`); DOM-verify Escalate/Needs-info; empty-state + narrow-viewport; adopt the synced design-system `dev_note()`/`humanize_id()` helpers for 630.
