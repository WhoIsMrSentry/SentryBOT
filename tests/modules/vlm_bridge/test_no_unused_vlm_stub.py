from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOTS = ["modules", "apps", "services", "config"]
FORBIDDEN_REFERENCES = [
    "modules.vlm_bridge.services.stub",
    "vlm_bridge.services.stub",
    "from .stub",
    "import stub",
    "services/stub.py",
    "services\\stub.py",
]


def _runtime_files():
    suffixes = {".py", ".json", ".yml", ".yaml", ".md", ".toml", ".ini"}
    for root_name in SCAN_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if any(part in {".venv", "__pycache__", ".pytest_cache"} for part in path.parts):
                continue
            yield path


def test_unused_vlm_stub_file_removed():
    assert not (ROOT / "modules/vlm_bridge/services/stub.py").exists()


def test_no_runtime_reference_to_unused_vlm_stub():
    hits = []
    for path in _runtime_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in FORBIDDEN_REFERENCES:
            if needle in text:
                hits.append(f"{path.relative_to(ROOT).as_posix()} contains {needle}")
    assert hits == []
