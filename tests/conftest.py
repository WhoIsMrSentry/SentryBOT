from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
root_s = str(ROOT)
if root_s not in sys.path:
    sys.path.insert(0, root_s)

_DATA_PROTECTED_PATTERNS = ("*.sqlite3", "*.db", "faces.json", "speaker_id.json")
_STATE_PROTECTED_FILES = ("world_memory.json", "arm_state.json")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--smoke-real",
        action="store_true",
        default=False,
        help="Disable workspace data/state snapshot rollback (for explicit hardware/live smoke runs).",
    )


def _snapshot_files(directory: Path, filenames_or_globs: tuple[str, ...]) -> tuple[dict[Path, bytes], set[Path]]:
    if not directory.is_dir():
        return {}, set()
    matched: set[Path] = set()
    for pat in filenames_or_globs:
        if "*" in pat or "?" in pat:
            matched.update(p for p in directory.glob(pat) if p.is_file())
        else:
            cand = directory / pat
            if cand.is_file():
                matched.add(cand)
    snapshots: dict[Path, bytes] = {}
    for path in matched:
        try:
            snapshots[path] = path.read_bytes()
        except OSError:
            pass
    return snapshots, matched


def _restore_files(directory: Path, snapshots: dict[Path, bytes], filenames_or_globs: tuple[str, ...]) -> None:
    if not directory.is_dir():
        return
    current: set[Path] = set()
    for pat in filenames_or_globs:
        if "*" in pat or "?" in pat:
            current.update(p for p in directory.glob(pat) if p.is_file())
        else:
            cand = directory / pat
            if cand.is_file():
                current.add(cand)
    for extra in current - set(snapshots.keys()):
        try:
            extra.unlink()
        except OSError:
            pass
    for path, content in snapshots.items():
        try:
            if path.is_file() and path.read_bytes() == content:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except OSError:
            # Skip locked singleton SQLite handles cleanly on Windows
            pass


@pytest.fixture(autouse=True)
def _isolate_runtime_state_and_data_dir(request: pytest.FixtureRequest):
    """Protect live workspace `.sentrybot_state/` and `data/` artifacts across non-`--smoke-real` tests."""
    if request.config.getoption("--smoke-real", default=False):
        yield
        return

    state_dir = ROOT / ".sentrybot_state"
    data_dir = ROOT / "data"
    state_snaps, _ = _snapshot_files(state_dir, _STATE_PROTECTED_FILES)
    data_snaps, _ = _snapshot_files(data_dir, _DATA_PROTECTED_PATTERNS)

    # Isolate world_memory.json proactively for memory-heavy test suites while restoring any prior state afterwards
    nodeid = getattr(request.node, "nodeid", "")
    if any(tok in nodeid for tok in ("world_memory", "memory_", "test_migration", "autonomy")):
        wm = state_dir / "world_memory.json"
        if wm.exists():
            try:
                wm.unlink()
            except OSError:
                pass

    try:
        yield
    finally:
        _restore_files(state_dir, state_snaps, _STATE_PROTECTED_FILES)
        _restore_files(data_dir, data_snaps, _DATA_PROTECTED_PATTERNS)
