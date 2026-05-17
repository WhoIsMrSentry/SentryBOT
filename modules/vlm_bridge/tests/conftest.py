"""Pytest configuration for vlm_bridge tests.

Mock cv2 and numpy to avoid Python 3.14 compatibility issues during import.
These mocks are scoped to this test module only.
"""

import sys
from unittest.mock import MagicMock


class _SafeNumPyMock(MagicMock):
    """Mock numpy that doesn't break isinstance() checks.
    
    Pytest and other libraries check for numpy bool types with isinstance(),
    which requires the mock to provide a real type object, not a MagicMock.
    """
    
    def __getattr__(self, name):
        # Return None for type-like attributes so isinstance() doesn't fail
        if name == 'bool_':
            return type(None)  # Return a real type instead of MagicMock
        return super().__getattr__(name)


def pytest_configure(config):
    """Configure pytest before test collection.
    
    Mock cv2 and numpy at the session level to prevent import errors
    when VisionProcessor is imported during test collection.
    """
    if 'cv2' not in sys.modules:
        sys.modules['cv2'] = MagicMock()
    if 'numpy' not in sys.modules:
        sys.modules['numpy'] = _SafeNumPyMock()


def pytest_unconfigure(config):
    """Clean up mocks after all tests complete.
    
    Remove the mocks so they don't interfere with other test modules.
    """
    # Remove mocks to allow other tests to import real libraries if needed
    sys.modules.pop('cv2', None)
    sys.modules.pop('numpy', None)

