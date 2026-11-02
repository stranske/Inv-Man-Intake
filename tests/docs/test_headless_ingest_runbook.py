"""Ensure the headless ingest runbook quickstart matches production layout rules."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

DOC_PATH = Path("docs/runbooks/headless_ingest.md")
_KEEP_FILES = frozenset({"summit_arc_investment_update.pdf", "summit_arc_track_record.xlsx"})


def _primary_inv_man_ingest_command(text: str) -> str:
    """Return the documented inv-man-ingest line from the primary bash fence."""

    fences = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)
    assert fences, "runbook must include a bash quickstart fence"
    primary = fences[0]
    for line in primary.splitlines():
        stripped = line.strip()
        if stripped.startswith("inv-man-ingest "):
            return stripped
    raise AssertionError("primary bash fence must include an inv-man-ingest command")


def _stage_bundle_like_runbook(repo_root: Path, bundle_dir: Path) -> Path:
    extraction = repo_root / "tests/fixtures/extraction"
    for name in _KEEP_FILES:
        shutil.copyfile(extraction / name, bundle_dir / name)
    payload = json.loads(
        (repo_root / "tests/fixtures/intake/pdf_primary_mixed_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    payload["files"] = [entry for entry in payload["files"] if entry["file_name"] in _KEEP_FILES]
    staged_bundle = bundle_dir / "mixed_bundle.json"
    staged_bundle.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return staged_bundle


def test_headless_ingest_runbook_quickstart_succeeds_on_fresh_layout(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    text = (repo_root / DOC_PATH).read_text(encoding="utf-8")
    command = _primary_inv_man_ingest_command(text)

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    staged_bundle = _stage_bundle_like_runbook(repo_root, bundle_dir)

    out_dir = tmp_path / "run-out"
    out_dir.mkdir()
    rendered = command.replace("$BUNDLE_DIR/mixed_bundle.json", str(staged_bundle)).replace(
        "./.run-out", str(out_dir)
    )

    argv = shlex.split(rendered)
    assert argv[0] == "inv-man-ingest"
    env = {**os.environ, "PYTHONPATH": str(repo_root / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "inv_man_intake.cli.ingest", *argv[1:]],
        cwd=repo_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert (out_dir / "run.json").is_file()
