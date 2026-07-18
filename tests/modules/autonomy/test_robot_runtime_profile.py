from __future__ import annotations

import json
from pathlib import Path

from modules.autonomy.services import robot_runtime_profile as profile


ROOT = Path(__file__).resolve().parents[3]


def test_profile_config_exists_and_loads():
    path = profile.profile_config_path(ROOT)
    assert path.exists(), path

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert "profiles" in raw

    cfg = profile.load_profile_config(ROOT)
    assert cfg["ok"] is True
    assert isinstance(cfg["profiles"], dict)

def test_resolve_runtime_profile():
    # Since we can't easily mock the global detect_runtime_target here without monkeypatch,
    # we just test that it returns the expected structure.
    st = profile.resolve_runtime_profile(ROOT)
    assert "ok" in st
    assert "target" in st
    assert st["profile_name"] == "raspberry_pi"
    assert "profile" in st

def test_status():
    st = profile.status(ROOT)
    assert "ok" in st
    assert "target" in st
    assert "allow_real_hardware" in st
