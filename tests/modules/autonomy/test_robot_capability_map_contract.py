from __future__ import annotations

import json
from pathlib import Path

from modules.autonomy.services import robot_capability_map as capmap


ROOT = Path(__file__).resolve().parents[3]


def test_capability_map_contract_markers():
    assert capmap.ROBOT_CAPABILITY_SOURCE_OF_TRUTH is True
    assert capmap.ROBOT_CAPABILITY_BOUNDARY_ROLE == "autonomy_read_only_capability_registry_adapter"
    assert capmap.ROBOT_CAPABILITY_CONFIG_PATH == "config/robot_capability_registry.json"


def test_capability_registry_file_exists_and_loads():
    path = capmap.registry_path(ROOT)
    assert path.exists(), path

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)

    registry = capmap.load_registry(ROOT)
    assert registry["ok"] is True
    assert registry["available"] is True
    assert registry["source"] == "config/robot_capability_registry.json"


def test_capability_status_is_read_only_and_safe():
    st = capmap.status(ROOT)
    assert st["read_only"] is True
    assert st["hardware_enabled"] is False
    assert st["armed"] is False
    assert isinstance(st["capabilities"], list)
    assert st["capability_count"] == len(st["capabilities"])


def test_capability_lookup_contract():
    names = capmap.list_capabilities(ROOT)
    assert isinstance(names, list)

    if names:
        item = capmap.get_capability(names[0], ROOT)
        assert item["name"] == names[0]
        assert item["available"] is True

    missing = capmap.get_capability("__missing_capability__", ROOT)
    assert missing["available"] is False
    assert missing["reason"] == "capability_not_found"
