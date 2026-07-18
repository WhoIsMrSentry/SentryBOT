from __future__ import annotations

from modules.gateway.services.bootstrap import _camera_hardware_available


def test_camera_hardware_false_when_not_included():
    cfg = {"include": {"camera": False}}
    assert _camera_hardware_available(cfg) is False


def test_camera_hardware_false_when_disabled_in_yaml(monkeypatch):
    cfg = {"include": {"camera": True}}
    import modules.camera.config_loader as cam_cfg
    monkeypatch.setattr(cam_cfg, "load_config", lambda: {"enabled": False})
    assert _camera_hardware_available(cfg) is False
