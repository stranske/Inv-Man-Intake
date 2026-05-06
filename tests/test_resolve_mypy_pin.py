from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_resolve_mypy_pin_falls_back_when_github_output_is_unwritable(tmp_path: Path) -> None:
    script = Path("tools/resolve_mypy_pin.py")
    output_dir = tmp_path / "outdir"
    output_dir.mkdir()

    env = dict(os.environ)
    env["GITHUB_OUTPUT"] = str(output_dir)
    env["MATRIX_PYTHON_VERSION"] = "3.13"

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0
    assert "warning: unable to write GITHUB_OUTPUT" in result.stderr
    assert "python-version=3.12" in result.stdout
