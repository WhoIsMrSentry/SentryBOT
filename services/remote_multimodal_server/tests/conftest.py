import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# When the whole repo test suites run in a single pytest process, sibling
# conftests (tests/modules/vlm_bridge) may have installed cv2/numpy mocks in
# sys.modules. Reload the real packages here so CV pipelines are testable.
for _mod in ("cv2", "numpy"):
    try:
        sys.modules.pop(_mod, None)
    except Exception:
        pass
try:
    importlib.import_module("numpy")
    importlib.import_module("cv2")
except Exception:
    pass
