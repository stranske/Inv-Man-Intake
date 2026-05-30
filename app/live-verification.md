# Live Verification Gate (Browser, No Python Install)

This gate validates that the stlite browser demo is usable by a non-technical reviewer with no local Python runtime.

## Exact Open/Serve Step

Use either option:

1. Direct open: open `app/index.html` in a browser.
2. Static serve (recommended): from repository root run `python -m http.server 8000` and open `http://127.0.0.1:8000/app/index.html`.

## Reviewer Checks

1. Confirm the page loads with the `Inv-Man-Intake` title.
2. In `Synthetic intake bundle`, choose `pdf_primary_mixed_bundle.json`.
3. Confirm `Final score` is visible as `0.7809`.
4. Confirm the `Explainability` table renders one or more component rows.
5. Confirm `Analyst queue` renders `owner_role` and `item_id`.

## Screenshot Evidence

![Live browser verification screenshot](./live-verification-screenshot.svg)

Stored screenshot artifact for PR verification after selecting `pdf_primary_mixed_bundle.json`.
