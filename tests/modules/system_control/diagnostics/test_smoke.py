from __future__ import annotations

from modules.system_control.diagnostics.xDiagnosticsService import create_app


def test_create_app():
    app = create_app()
    assert app is not None


def test_self_heal_enabled_in_config():
    from modules.system_control.diagnostics.config_loader import load_config

    cfg = load_config()
    heal = cfg.get("self_heal") or {}
    assert heal.get("enabled") is True
    camera = ((cfg.get("checks") or {}).get("camera") or {}).get("heal") or {}
    speech = ((cfg.get("checks") or {}).get("speech") or {}).get("heal") or {}
    assert camera.get("path") == "/camera/start"
    assert speech.get("path") == "/speech/start"
