from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest

import sentrybot


def test_bluetooth_output_sets_only_output_sink(monkeypatch):
    commands = []

    def fake_command(command, timeout_s):
        commands.append(command)
        if command[:2] == ["bluetoothctl", "devices"]:
            return SimpleNamespace(returncode=0, stdout="Device AA:BB:CC:DD:EE:FF Pet Speaker\n", stderr="")
        if command[:2] == ["bluetoothctl", "connect"]:
            return SimpleNamespace(returncode=0, stdout="Connection successful\n", stderr="")
        if command[:3] == ["pactl", "list", "short"]:
            return SimpleNamespace(
                returncode=0,
                stdout="42\tbluetooth_AA_BB_CC_DD_EE_FF.a2dp-sink\tmodule\n",
                stderr="",
            )
        if command[:2] == ["pactl", "set-default-sink"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(sentrybot.shutil, "which", lambda _: "/usr/bin/fake")
    monkeypatch.setattr(sentrybot, "_command", fake_command)
    monkeypatch.delenv("PULSE_SOURCE", raising=False)
    sink = sentrybot._enable_bluetooth_output(
        {"startup": {"bluetooth": {"command_timeout_s": 1}}},
        "AA:BB:CC:DD:EE:FF",
    )

    assert sink == "bluetooth_AA_BB_CC_DD_EE_FF.a2dp-sink"
    assert sentrybot.os.environ["PULSE_SINK"] == sink
    assert "PULSE_SOURCE" not in sentrybot.os.environ
    assert ["bluetoothctl", "connect", "AA:BB:CC:DD:EE:FF"] in commands


def test_preflight_requires_strict_i2s_device(monkeypatch):
    class TargetError(RuntimeError):
        pass

    monkeypatch.setattr(sentrybot.shutil, "which", lambda _: "/usr/bin/fake")
    monkeypatch.setattr("modules.common.runtime_target.assert_raspberry_pi", lambda: None)
    config = {
        "startup": {"preflight": {"enabled": True, "required_python_modules": [], "required_commands": []}},
        "speech": {"audio": {"device": "plughw:0,0", "strict_device": False}},
    }
    assert "i2s_input_not_strict" in sentrybot._preflight_failures(config)


def test_load_startup_config(monkeypatch):
    monkeypatch.setattr("modules.common.config_loader.load_agent_config", lambda: {"robot": {"name": "SentryBOT"}})
    cfg = sentrybot._load_startup_config()
    assert isinstance(cfg, dict)
    assert cfg.get("robot", {}).get("name") == "SentryBOT"


def test_agent_config_loader_and_lazy_tui_imports(monkeypatch):
    from modules.common.config_loader import load_agent_config, resolve_agent_cfg_path

    assert callable(load_agent_config)
    assert callable(resolve_agent_cfg_path)

    # Importing sentrybot must keep heavy TUI modules lazy until actually invoked
    sys.modules.pop("modules.runtime_console.tui_v2", None)
    sys.modules.pop("modules.runtime_console.system_info_tui", None)

    reloaded = importlib.reload(sentrybot)
    assert "modules.runtime_console.tui_v2" not in sys.modules
    assert "modules.runtime_console.system_info_tui" not in sys.modules

    monkeypatch.setenv("SENTRYBOT_TUI_DELAY_S", "0")
    assert reloaded._wait_for_ready_signal(ready_url=None) is True


def test_launcher_preserves_nonzero_system_exit_and_no_delay(monkeypatch):
    monkeypatch.setattr(sentrybot, "_configure_logging", lambda: None)
    monkeypatch.setattr(sentrybot, "_load_startup_config", lambda: {"startup": {"preflight": {"enabled": False}}})
    monkeypatch.setattr(sentrybot, "_run_sysinfo_once", lambda: None)

    wait_called = False

    def _fake_wait(*_args, **_kwargs):
        nonlocal wait_called
        wait_called = True
        return True

    def _raise_exit(_args):
        raise SystemExit(7)

    monkeypatch.setattr(sentrybot, "_wait_for_ready_signal", _fake_wait)
    monkeypatch.setattr(sentrybot, "_run_tui", _raise_exit)

    rc = sentrybot.main(["--no-run", "--no-delay"])
    assert rc == 7
    assert wait_called is False

    with pytest.raises(SystemExit) as exc_info:
        sentrybot.main(["--help"])
    assert exc_info.value.code == 0