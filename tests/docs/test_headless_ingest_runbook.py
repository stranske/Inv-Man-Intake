"""Ensure the headless ingest runbook quickstart matches production layout rules."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

DOC_PATH = Path("docs/runbooks/headless_ingest.md")


def _primary_quickstart_script(text: str) -> str:
    """Return the primary bash quickstart (staging + inv-man-ingest), excluding equivalents."""

    fences = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)
    assert fences, "runbook must include a bash quickstart fence"
    lines: list[str] = []
    for line in fences[0].splitlines():
        if "Equivalent module form" in line:
            break
        lines.append(line)
    script = "\n".join(lines).strip()
    assert "inv-man-ingest " in script, "primary bash fence must include inv-man-ingest"
    return script


def test_headless_ingest_runbook_quickstart_succeeds_on_fresh_layout(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / DOC_PATH).read_text(encoding="utf-8")
    script = _primary_quickstart_script(text)

    out_dir = tmp_path / "run-out"
    # Substitute the documented --out target with an isolated temp directory.
    rendered = script.replace("./.run-out", shlex.quote(str(out_dir)))

    proc = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", rendered],
        cwd=repo_root,
        env=os.environ.copy(),
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert (out_dir / "run.json").is_file()
