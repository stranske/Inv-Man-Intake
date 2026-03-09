"""Packaging installation smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_editable_install_succeeds_in_clean_venv(tmp_path: Path) -> None:
    """Editable install should succeed in an isolated virtual environment."""
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    bin_dir = "Scripts" if os.name == "nt" else "bin"
    python_exe = venv_dir / bin_dir / ("python.exe" if os.name == "nt" else "python")

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    subprocess.run(
        [
            str(python_exe),
            "-m",
            "pip",
            "install",
            "-e",
            str(PROJECT_ROOT),
            "--no-build-isolation",
        ],
        check=True,
        cwd=PROJECT_ROOT,
        env=env,
    )

    result = subprocess.run(
        [str(python_exe), "-c", "import my_project; print(my_project.__version__)"],
        check=True,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "0.1.0"
