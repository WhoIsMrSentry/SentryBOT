"""Pytest configuration for vlm_bridge tests.

Mock cv2 and numpy only when unimportable, and remove only mocks injected here.
"""

import sys
from unittest.mock import MagicMock

_MOCKED_MODULES: set[str] = set()


class _SafeNumPyMock(MagicMock):
    """Mock numpy that doesn't break isinstance() checks."""

    def __getattr__(self, name):
        if name == "bool_":
            return type(None)
        return super().__getattr__(name)


def pytest_configure(config):
    """Inject scoped mocks only if cv2 or numpy cannot be imported."""
    if "cv2" not in sys.modules:
        try:
            import cv2  # noqa: F401
        except Exception:
            sys.modules["cv2"] = MagicMock()
            _MOCKED_MODULES.add("cv2")
    if "numpy" not in sys.modules:
        try:
            import numpy  # noqa: F401
        except Exception:
            sys.modules["numpy"] = _SafeNumPyMock()
            _MOCKED_MODULES.add("numpy")


def pytest_unconfigure(config):
    """Clean up only module mocks injected by this conftest."""
    for mod_name in list(_MOCKED_MODULES):
        sys.modules.pop(mod_name, None)
    _MOCKED_MODULES.clear()

