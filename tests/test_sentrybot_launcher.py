from __future__ import annotations

from types import SimpleNamespace

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
            return SimpleNamespace(returncode=0, stdout="42\tbluetooth_AA_BB_CC_DD_EE_FF.a2dp-sink\tmodule\n", stderr="")
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