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
