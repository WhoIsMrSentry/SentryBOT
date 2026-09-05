#!/usr/bin/env python3
"""SentryBOT unified launcher with startup validation and optional Bluetooth output."""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from modules.runtime_console.system_info_tui import main as sysinfo_main
from modules.runtime_console.tui_v2 import main as tui_main

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger("sentrybot.launcher")


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_startup_config() -> dict[str, Any]:
    from modules.common.config_loader import load_agent_config

    return _as_mapping(load_agent_config())


def _command(command: list[str], timeout_s: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        timeout=max(0.1, timeout_s),
    )


def _configure_logging() -> None:
    try:
        from modules.runtime_console.logwrapper import init_logging

        init_logging()
    except Exception as exc:
        logging.basicConfig(level=logging.INFO)
        LOGGER.warning("central logging unavailable during startup: %s", exc)


def _preflight_failures(config: dict[str, Any]) -> list[str]:
    startup = _as_mapping(config.get("startup"))
    checks = _as_mapping(startup.get("preflight"))
    if not bool(checks.get("enabled", True)):
        return []

    failures: list[str] = []
    if bool(checks.get("require_raspberry_pi", True)):
        try:
            from modules.common.runtime_target import assert_raspberry_pi

            assert_raspberry_pi()
        except Exception as exc:
            failures.append(f"runtime_target: {exc}")

    for module_name in checks.get("required_python_modules", []):
        name = str(module_name).strip()
        if name and importlib.util.find_spec(name) is None:
            failures.append(f"python_module_missing:{name}")

    for command in checks.get("required_commands", []):
        name = str(command).strip()
        if name and shutil.which(name) is None:
            failures.append(f"command_missing:{name}")

    speech = _as_mapping(config.get("speech"))
    audio = _as_mapping(speech.get("audio"))
    if bool(checks.get("require_i2s_input", True)):
        device = str(audio.get("device") or "").strip()
        if not device:
            failures.append("i2s_input_device_missing")
        elif not bool(audio.get("strict_device", False)):
            failures.append("i2s_input_not_strict")
    return failures


def _parse_bluetooth_devices(stdout: str) -> list[tuple[str, str]]:
    devices: list[tuple[str, str]] = []
    for line in stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) >= 3 and parts[0].lower() == "device":
            devices.append((parts[1], parts[2]))
    return devices


def _select_bluetooth_device(devices: list[tuple[str, str]], explicit: str | None) -> tuple[str, str]:
    if explicit:
        normalized = explicit.strip().lower()
        for address, name in devices:
            if address.lower() == normalized:
                return address, name
        raise RuntimeError(f"requested_bluetooth_device_not_paired:{explicit}")
    if not devices:
        raise RuntimeError("no_paired_bluetooth_output_device")
    if len(devices) == 1:
        return devices[0]
    if not sys.stdin.isatty():
        raise RuntimeError("bluetooth_device_selection_requires_tty")
    print("\nBluetooth output devices:")
    for index, (address, name) in enumerate(devices, start=1):
        print(f"  {index}. {name} [{address}]")
    raw = input("Select output device number: ").strip()
    try:
        selected = int(raw)
    except ValueError as exc:
        raise RuntimeError("invalid_bluetooth_device_selection") from exc
    if selected < 1 or selected > len(devices):
        raise RuntimeError("bluetooth_device_selection_out_of_range")
    return devices[selected - 1]


def _find_bluetooth_sink(pactl: str, address: str, timeout_s: float) -> str:
    listed = _command([pactl, "list", "short", "sinks"], timeout_s)
    if listed.returncode != 0:
        raise RuntimeError(f"pactl_list_sinks_failed:{listed.stderr.strip()}")
    token = address.replace(":", "_").lower()
    for line in listed.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and token in fields[1].lower():
            return fields[1]
    raise RuntimeError(f"bluetooth_sink_not_found:{address}")


def _enable_bluetooth_output(config: dict[str, Any], explicit_device: str | None) -> str:
    startup = _as_mapping(config.get("startup"))
    bluetooth = _as_mapping(startup.get("bluetooth"))
    timeout_s = float(bluetooth.get("command_timeout_s", 20.0))
    bluetoothctl = str(bluetooth.get("bluetoothctl_command", "bluetoothctl"))
    pactl = str(bluetooth.get("pactl_command", "pactl"))
    for command in (bluetoothctl, pactl):
        if shutil.which(command) is None:
            raise RuntimeError(f"bluetooth_dependency_missing:{command}")

    paired = _command([bluetoothctl, "devices", "Paired"], timeout_s)
    if paired.returncode != 0:
        paired = _command([bluetoothctl, "devices"], timeout_s)
    address, name = _select_bluetooth_device(_parse_bluetooth_devices(paired.stdout), explicit_device)

    connected = _command([bluetoothctl, "connect", address], timeout_s)
    if connected.returncode != 0:
        raise RuntimeError(f"bluetooth_connect_failed:{address}:{connected.stderr.strip()}")

    sink = _find_bluetooth_sink(pactl, address, timeout_s)
    selected = _command([pactl, "set-default-sink", sink], timeout_s)
    if selected.returncode != 0:
        raise RuntimeError(f"bluetooth_default_sink_failed:{sink}:{selected.stderr.strip()}")

    os.environ["PULSE_SINK"] = sink
    os.environ["SENTRYBOT_AUDIO_OUTPUT_SINK"] = sink
    LOGGER.info("Bluetooth output connected: %s [%s] -> %s", name, address, sink)
    return sink


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentryBOT Ultimate Launcher")
    parser.add_argument("--no-run", action="store_true", help="show the TUI without starting robot services")
    parser.add_argument("--bluetooth", action="store_true", help="select a paired Bluetooth device for output only")
    parser.add_argument("--bluetooth-device", help="paired Bluetooth device MAC address; skips interactive selection")
    args, unknown = parser.parse_known_args(argv)

    _configure_logging()
    config = _load_startup_config()
    if not args.no_run:
        failures = _preflight_failures(config)
        if failures:
            for failure in failures:
                LOGGER.error("startup preflight failed: %s", failure)
            print("SentryBOT startup blocked; inspect logs/errors.log and logs/warnings.log.", file=sys.stderr)
            return 2
        if args.bluetooth:
            try:
                _enable_bluetooth_output(config, args.bluetooth_device)
            except Exception as exc:
                LOGGER.error("Bluetooth output setup failed: %s", exc)
                print(f"Bluetooth output setup failed: {exc}", file=sys.stderr)
                return 3

    print("\n\x1b[1;36m--- SENTRYBOT SYSTEM INITIALIZING ---\x1b[0m\n")
    try:
        sysinfo_main(["--once"])
    except Exception as exc:
        LOGGER.warning("system information display failed: %s", exc)
    try:
        print("\n\x1b[2mLoading Control Center...\x1b[0m")
        time.sleep(1.0)

        tui_args = ["--alt"]
        if not args.no_run:
            tui_args.append("--run")
        else:
            tui_args.append("--no-run")
        tui_args.extend(unknown)
        return tui_main(tui_args)
    except (KeyboardInterrupt, SystemExit):
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)