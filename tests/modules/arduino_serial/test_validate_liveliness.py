"""Contract tests for the firmware liveliness command (builder + validator)."""

from __future__ import annotations

from modules.arduino_serial.contract import (
    build_liveliness_cmd,
    validate_arduino_payload,
    validate_liveliness_cmd,
    LIVELINESS_AMPLITUDE_MAX_DEG,
    LIVELINESS_PERIOD_MIN_MS,
)


def test_builder_shapes_payload():
    cmd = build_liveliness_cmd(True, mode="breathe", amplitude_deg=6, period_ms=4000, pan_center=90, tilt_center=95)
    assert cmd["cmd"] == "liveliness"
    assert cmd["enable"] is True
    assert cmd["mode"] == "breathe"
    assert cmd["amplitude_deg"] == 6.0
    assert cmd["period_ms"] == 4000
    assert cmd["pan_center"] == 90.0


def test_enable_true_valid_passes():
    cmd = build_liveliness_cmd(True, mode="breathe", amplitude_deg=5, period_ms=3000)
    assert validate_arduino_payload(cmd) is None


def test_disable_needs_no_params():
    assert validate_arduino_payload(build_liveliness_cmd(False)) is None


def test_enable_requires_bool():
    assert validate_liveliness_cmd({"cmd": "liveliness"}) is not None
    assert validate_liveliness_cmd({"cmd": "liveliness", "enable": "yes"}) is not None


def test_rejects_unknown_mode():
    cmd = build_liveliness_cmd(True, mode="rave")
    assert "mode" in (validate_arduino_payload(cmd) or "")


def test_rejects_excessive_amplitude():
    cmd = build_liveliness_cmd(True, amplitude_deg=LIVELINESS_AMPLITUDE_MAX_DEG + 5)
    assert "amplitude_deg" in (validate_arduino_payload(cmd) or "")


def test_rejects_too_short_period():
    cmd = build_liveliness_cmd(True, period_ms=LIVELINESS_PERIOD_MIN_MS - 1)
    assert "period_ms" in (validate_arduino_payload(cmd) or "")


def test_rejects_out_of_range_center():
    cmd = build_liveliness_cmd(True, pan_center=999)
    assert "pan_center" in (validate_arduino_payload(cmd) or "")


def test_other_cmd_passes_through_validator():
    # validate_liveliness_cmd ignores non-liveliness payloads
    assert validate_liveliness_cmd({"cmd": "hello"}) is None
