"""Pytest runtime configuration shared across the test suite."""

from __future__ import annotations

import pytest


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config: object) -> int:  # pragma: no cover - xdist hook
    """Stabilize CI runs when workflows invoke pytest with ``-n auto``.

    The reusable CI workflow enables xdist automatically. Returning ``1`` keeps
    behavior deterministic while still allowing the workflow to pass ``-n auto``.
    """

    return 1


def pytest_configure(config: pytest.Config) -> None:
    """Force deterministic xdist behavior when CI injects ``-n auto``.

    Some CI workflows append ``-n auto`` dynamically. Normalizing it to a
    single worker keeps behavior equivalent to local sequential runs and avoids
    CI-only ordering/race failures.
    """

    numprocesses = getattr(config.option, "numprocesses", None)
    if numprocesses == "auto":
        config.option.numprocesses = 1
