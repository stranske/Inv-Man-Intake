"""Every public entry module must import cleanly as the first import."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
ENTRY_MODULES = (
    "inv_man_intake.packet",
    "inv_man_intake.export.image_export",
    "inv_man_intake.assist.intake_assistant",
)


@pytest.mark.parametrize("module", ENTRY_MODULES)
def test_module_imports_without_a_warm_sys_modules(module: str) -> None:
    """A fresh interpreter must not depend on another module breaking an import cycle."""

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(SRC), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
