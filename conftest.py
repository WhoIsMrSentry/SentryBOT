"""Repository-level pytest hooks."""
from __future__ import annotations

from pathlib import Path


def pytest_configure(config) -> None:
    """Redirect legacy ``pytest modules`` invocations to ``tests/``."""
    if len(config.args) != 1:
        return
    target = Path(str(config.args[0]))
    if target.name == "modules":
        config.args[0] = "tests"
