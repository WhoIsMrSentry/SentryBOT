from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
root_s = str(ROOT)
if root_s not in sys.path:
    sys.path.insert(0, root_s)


@pytest.fixture(autouse=True)
def _isolate_world_memory_file_for_tests(request):
    """Keep real robot memory safe while preventing cross-test pollution."""
    nodeid = getattr(request.node, "nodeid", "")
    touches_memory = (
        "world_memory" in nodeid
        or "memory_" in nodeid
        or "test_migration" in nodeid
        or "autonomy" in nodeid
    )
    if not touches_memory:
        yield
        return

    state_dir = ROOT / ".sentrybot_state"
    memory_file = state_dir / "world_memory.json"
    had_file = memory_file.exists()
    original = memory_file.read_bytes() if had_file else None

    if had_file:
        memory_file.unlink()

    try:
        yield
    finally:
        if memory_file.exists():
            memory_file.unlink()
        if had_file:
            state_dir.mkdir(parents=True, exist_ok=True)
            memory_file.write_bytes(original)
