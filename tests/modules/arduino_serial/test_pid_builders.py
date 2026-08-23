from modules.arduino_serial.contract import (
    build_pid_enable_cmd,
    build_pid_set_cmd,
    build_pid_status_cmd,
    validate_arduino_payload,
)


def test_build_pid_enable_cmd():
    payload = build_pid_enable_cmd(0, True)
    assert payload == {"cmd": "pid_enable", "id": 0, "enable": True}
    assert validate_arduino_payload(payload) is None


def test_build_pid_set_cmd():
    payload = build_pid_set_cmd(1, target=40.0)
    assert payload["cmd"] == "pid_set"
    assert payload["id"] == 1
    assert payload["target"] == 40.0
    assert validate_arduino_payload(payload) is None


def test_build_pid_status_cmd():
    payload = build_pid_status_cmd(0)
    assert payload == {"cmd": "pid_status", "id": 0}
    assert validate_arduino_payload(payload) is None
