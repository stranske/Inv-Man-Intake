# Live Verification Gate (Browser, No Python Install)

This gate validates that the stlite browser demo is usable by a non-technical reviewer with no local Python runtime. The durable PR evidence must come from the headless-browser verifier below; the older SVG fixture is supporting documentation only and is not sufficient browser evidence.

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

## Headless Browser Evidence

Install the optional browser verifier dependencies and run:

```bash
python -m pip install -e ".[app,browser]"
python -m playwright install chromium
python scripts/verify_stlite_browser_demo.py
```

On systems with Chrome already installed, the verifier can use it directly:

```bash
python scripts/verify_stlite_browser_demo.py \
  --chrome-executable "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

The command starts a local static server, opens `app/index.html` in a real headless browser, waits for `pdf_primary_mixed_bundle.json`, `Final score` `0.7809`, `Explainability`, and `Analyst queue`, then writes:

- `app/live-verification-browser.png`
- `app/live-verification-browser.log`
- `app/live-verification-browser.json`

## Historical Screenshot

![Live browser verification screenshot](./live-verification-screenshot.svg)

Stored synthetic screenshot from the original demo PR after selecting `pdf_primary_mixed_bundle.json`. Use the headless-browser verifier above for current PR verification.
