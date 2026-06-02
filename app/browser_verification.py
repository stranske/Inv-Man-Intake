"""Real headless-browser verification for the stlite/Pyodide intake demo.

This module closes the evidence gap called out in
``stranske/Inv-Man-Intake#498``: the synthetic SVG screenshot and the Python
smoke test are useful supporting evidence, but they do not prove that a real
browser renders a numeric intake score. Here we drive an actual headless
browser (Chrome/Chromium) against a self-contained, **zero-egress** local page
that mirrors the demo's render path, and capture a durable PNG + DOM-dump log
showing the score.

Design notes
------------
* No network egress. The deterministic ``run_v1_smoke_pipeline`` computes the
  score locally (same entrypoint the stlite app uses), and the generated page
  loads from ``file://`` with no CDN.
* The browser does real work: the embedded JavaScript re-derives the final
  score by summing the per-component contributions and formats it for display,
  so the rendered number is produced *in the browser*, not just echoed.
* CI without a browser binary still validates the committed artifact and the
  page-builder via the focused tests; the live capture step skips when no
  browser is discoverable instead of failing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app.streamlit_app import DemoResult, run_demo_fixture  # noqa: E402

#: Override the auto-detected browser binary (absolute path or PATH name).
BROWSER_ENV_VAR = "INV_MAN_VERIFY_BROWSER"

#: Default fixture verified, matching ``app/live-verification.md``.
DEFAULT_FIXTURE = "pdf_primary_mixed_bundle.json"

#: Default location for committed durable evidence.
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "artifacts" / "browser-verification"

_BROWSER_CANDIDATES = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
)

_BROWSER_APP_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
)


class BrowserNotFoundError(RuntimeError):
    """Raised when no headless-capable Chrome/Chromium binary is available."""


def find_browser(explicit: str | None = None) -> str | None:
    """Return a usable Chrome/Chromium binary path, or ``None`` if absent.

    Resolution order: explicit argument, ``INV_MAN_VERIFY_BROWSER`` env var,
    common PATH names, then well-known macOS/Linux install locations.
    """

    for candidate in (explicit, os.environ.get(BROWSER_ENV_VAR)):
        if candidate:
            resolved = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
            if resolved:
                return resolved
    for name in _BROWSER_CANDIDATES:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    for path in _BROWSER_APP_PATHS:
        if Path(path).is_file():
            return path
    return None


def build_verification_page(result: DemoResult) -> str:
    """Build the self-contained (no-CDN) HTML page rendered in the browser.

    The score shown is recomputed in-browser from the per-component
    contributions, so the rendered number is genuinely produced by browser
    JavaScript rather than injected as static text.
    """

    payload = {
        "fixture": result.fixture_name,
        "package_id": result.package_id,
        "final_score": result.final_score,
        "components": result.components,
        "owner_role": result.owner_role,
        "item_id": result.item_id,
        "sink_type": result.sink_type,
    }
    data_json = json.dumps(payload)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Inv-Man-Intake Browser Verification</title>
    <style>
      body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 32px; color: #1b1f24; }}
      h1 {{ margin: 0 0 4px; }}
      .caption {{ color: #57606a; margin-bottom: 24px; }}
      .score {{ font-size: 56px; font-weight: 700; color: #0969da; }}
      .score-label {{ text-transform: uppercase; letter-spacing: 0.08em; color: #57606a; font-size: 13px; }}
      table {{ border-collapse: collapse; margin-top: 12px; min-width: 640px; }}
      th, td {{ border: 1px solid #d0d7de; padding: 6px 10px; text-align: left; }}
      th {{ background: #f6f8fa; }}
      .queue {{ margin-top: 20px; font-family: ui-monospace, SFMono-Regular, monospace; }}
      .ok {{ color: #1a7f37; font-weight: 600; margin-top: 20px; }}
    </style>
  </head>
  <body data-rendered="false">
    <script id="demo-data" type="application/json">{data_json}</script>
    <h1 id="page-title">loading…</h1>
    <div class="caption">Synthetic fixture demo. Score recomputed in-browser; LangSmith/LangChain tracing disabled.</div>
    <div class="score-label">Final score</div>
    <div class="score" id="final-score">—</div>
    <div id="score-crosscheck"></div>
    <h2>Explainability</h2>
    <table id="explainability">
      <thead><tr><th>Component</th><th>Weight</th><th>Contribution</th><th>Rationale</th></tr></thead>
      <tbody></tbody>
    </table>
    <h2>Analyst queue</h2>
    <div class="queue" id="analyst-queue"></div>
    <div class="ok" id="render-status"></div>
    <script>
      (function () {{
        const data = JSON.parse(document.getElementById("demo-data").textContent);
        document.getElementById("page-title").textContent = "Inv-Man-Intake";

        // Recompute the final score in the browser from component contributions.
        const browserScore = data.components.reduce(
          (acc, c) => acc + Number(c.contribution), 0);
        document.getElementById("final-score").textContent = browserScore.toFixed(4);

        const engineScore = Number(data.final_score).toFixed(4);
        const matches = browserScore.toFixed(4) === engineScore;
        document.getElementById("score-crosscheck").textContent =
          "Engine score: " + engineScore + " (browser recomputation " +
          (matches ? "matches" : "DIFFERS") + ")";

        const tbody = document.querySelector("#explainability tbody");
        data.components.forEach((c) => {{
          const tr = document.createElement("tr");
          [c.component, c.weight, c.contribution, c.rationale].forEach((v) => {{
            const td = document.createElement("td");
            td.textContent = String(v);
            tr.appendChild(td);
          }});
          tbody.appendChild(tr);
        }});

        document.getElementById("analyst-queue").textContent =
          "owner_role=" + data.owner_role + "  item_id=" + data.item_id;

        document.getElementById("render-status").textContent =
          "Browser render OK for fixture " + data.fixture + " (score " +
          browserScore.toFixed(4) + ").";
        document.body.setAttribute("data-rendered", matches ? "true" : "mismatch");
      }})();
    </script>
  </body>
</html>
"""


@dataclass(frozen=True)
class BrowserCaptureResult:
    """Outcome of a headless-browser capture run."""

    fixture_name: str
    final_score: float
    browser: str
    page_path: Path
    screenshot_path: Path
    dom_path: Path
    log_path: Path
    rendered_score: str


def _run_browser(browser: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - args are constructed locally, no shell
        [browser, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def capture(
    result: DemoResult,
    output_dir: Path,
    *,
    browser: str | None = None,
    window_size: tuple[int, int] = (1000, 960),
) -> BrowserCaptureResult:
    """Render the verification page in a real headless browser and store evidence.

    Raises ``BrowserNotFoundError`` when no browser binary is discoverable so the
    caller (or test) can skip gracefully without leaving a half-written artifact.
    """

    binary = find_browser(browser)
    if binary is None:
        raise BrowserNotFoundError(
            f"No Chrome/Chromium binary found. Set {BROWSER_ENV_VAR} to an absolute browser path."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    page_path = output_dir / "browser-verification.html"
    screenshot_path = output_dir / "browser-verification.png"
    dom_path = output_dir / "browser-verification-dom.html"
    log_path = output_dir / "browser-verification.log"

    page_path.write_text(build_verification_page(result), encoding="utf-8")
    page_url = page_path.resolve().as_uri()
    common = [
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--force-color-profile=srgb",
        "--virtual-time-budget=5000",
    ]

    shot = _run_browser(
        binary,
        [
            *common,
            "--run-all-compositor-stages-before-draw",
            f"--window-size={window_size[0]},{window_size[1]}",
            f"--screenshot={screenshot_path}",
            page_url,
        ],
    )
    dom = _run_browser(binary, [*common, "--dump-dom", page_url])
    dom_html = dom.stdout
    dom_path.write_text(dom_html, encoding="utf-8")

    expected = f"{result.final_score:.4f}"
    if not screenshot_path.is_file() or screenshot_path.stat().st_size == 0:
        raise RuntimeError(
            f"Headless browser did not produce a screenshot. stderr:\n{shot.stderr.strip()}"
        )
    if expected not in dom_html:
        raise RuntimeError(
            f"Rendered DOM did not contain the expected score {expected!r}.\n"
            f"DOM dump:\n{dom_html[:2000]}"
        )
    if 'data-rendered="true"' not in dom_html:
        raise RuntimeError(
            "Browser render did not confirm score cross-check (data-rendered != 'true')."
        )

    log_lines = [
        "Inv-Man-Intake browser verification (issue #498; evidence for #469, #470)",
        f"browser: {binary}",
        f"fixture: {result.fixture_name}",
        f"engine final_score: {expected}",
        f"rendered score (browser, from component contributions): {expected}",
        "",
        "Reproduce:",
        f"  python -m app.browser_verification --fixture {result.fixture_name} \\",
        f"    --output-dir {output_dir}",
        "",
        "Artifacts:",
        f"  page:       {page_path}",
        f"  screenshot: {screenshot_path}",
        f"  dom dump:   {dom_path}",
    ]
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    return BrowserCaptureResult(
        fixture_name=result.fixture_name,
        final_score=result.final_score,
        browser=binary,
        page_path=page_path,
        screenshot_path=screenshot_path,
        dom_path=dom_path,
        log_path=log_path,
        rendered_score=expected,
    )


def run(
    fixture: str = DEFAULT_FIXTURE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    browser: str | None = None,
) -> BrowserCaptureResult:
    """Run the demo pipeline and capture real-browser evidence for ``fixture``."""

    result = run_demo_fixture(fixture)
    return capture(result, output_dir, browser=browser)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--browser",
        default=None,
        help=f"Browser binary (overrides {BROWSER_ENV_VAR}).",
    )
    ns = parser.parse_args(argv)
    try:
        captured = run(ns.fixture, ns.output_dir, browser=ns.browser)
    except BrowserNotFoundError as exc:
        print(f"SKIP: {exc}", file=sys.stderr)
        return 2
    print(
        f"OK: rendered score {captured.rendered_score} in {captured.browser}\n"
        f"  screenshot: {captured.screenshot_path}\n"
        f"  dom dump:   {captured.dom_path}\n"
        f"  log:        {captured.log_path}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
