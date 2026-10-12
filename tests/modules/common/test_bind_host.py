"""Bind-host defaults stay on loopback unless config or env opts into LAN."""

from __future__ import annotations

from modules.common.bind_host import apply_bind_host, resolve_bind_host


def test_resolve_bind_host_defaults_to_loopback():
    assert resolve_bind_host(None) == "127.0.0.1"
    assert resolve_bind_host("") == "127.0.0.1"
    assert resolve_bind_host("0.0.0.0") == "0.0.0.0"


def test_resolve_bind_host_env_overrides_config(monkeypatch):
    monkeypatch.setenv("CAM_HOST", "0.0.0.0")
    assert resolve_bind_host("127.0.0.1", "CAM_HOST") == "0.0.0.0"


def test_apply_bind_host_keeps_existing_server_keys(monkeypatch):
    monkeypatch.delenv("AUTONOMY_HOST", raising=False)
    cfg = apply_bind_host({"server": {"host": "0.0.0.0", "port": 8100}}, "AUTONOMY_HOST")
    assert cfg["server"]["host"] == "0.0.0.0"
    assert cfg["server"]["port"] == 8100
