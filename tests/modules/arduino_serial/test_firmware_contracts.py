"""Contract and safety-invariant tests for Arduino/ESP32 firmware sources."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from modules.arduino_serial.contract_validators import SERVO_BOUNDS

REPO_ROOT = Path(__file__).resolve().parents[3]
XMAIN_DIR = REPO_ROOT / "arduino" / "firmware" / "xMain"
ESP_DIR = REPO_ROOT / "arduino" / "firmware" / "esp_bridge"
ARDUINO_CFG_YML = REPO_ROOT / "modules" / "arduino_serial" / "config" / "config.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_int_macro(source: str, name: str) -> int:
    match = re.search(rf"^\s*#define\s+{re.escape(name)}\s+(-?\d+)", source, re.MULTILINE)
    assert match is not None, f"Macro {name} not found"
    return int(match.group(1))


def test_esp_mdns_and_port_match_pi_config():
    cfg_yml = yaml.safe_load(_read(ARDUINO_CFG_YML))
    esp_cfg = _read(ESP_DIR / "config.h")

    mdns = re.search(r'#define\s+MDNS_HOSTNAME\s+"([^"]+)"', esp_cfg)
    assert mdns is not None
    port = _extract_int_macro(esp_cfg, "HTTP_PORT")

    expected_host = f"{mdns.group(1)}.local:{port}"
    assert expected_host in str(cfg_yml.get("esp_base_url", ""))
    assert 'WIFI_SSID "SentryBOT"' not in esp_cfg
    assert 'WIFI_PASS "SentryBOT"' not in esp_cfg
    assert "BRIDGE_AUTH_TOKEN" in esp_cfg
    assert "PRIORITY_WEB" not in esp_cfg
    assert "PRIORITY_WIFI" not in esp_cfg


def test_web_ui_servo_buttons_respect_mechanical_bounds_and_uses_cached_state():
    xconfig = _read(XMAIN_DIR / "xConfig.h")
    index_html = _read(ESP_DIR / "index.h")

    pan_min = _extract_int_macro(xconfig, "PAN_MIN")
    pan_max = _extract_int_macro(xconfig, "PAN_MAX")
    tilt_min = _extract_int_macro(xconfig, "TILT_MIN")
    tilt_max = _extract_int_macro(xconfig, "TILT_MAX")

    assert (float(pan_min), float(pan_max)) == SERVO_BOUNDS[0]
    assert (float(tilt_min), float(tilt_max)) == SERVO_BOUNDS[1]

    matches = re.findall(r"cmd:'set_servo'\s*,\s*index:(\d+)\s*,\s*deg:(\d+)", index_html)
    assert matches, "Expected raw servo buttons in esp_bridge/index.h"
    for idx_s, deg_s in matches:
        idx, deg = int(idx_s), int(deg_s)
        lo, hi = SERVO_BOUNDS[idx]
        assert lo <= deg <= hi, f"Button deg={deg} outside SERVO_BOUNDS[{idx}]=({lo},{hi})"

    assert "cmd:'estop_clear'" in index_html
    assert "fetch('/state')" in index_html
    poll_section = index_html[index_html.index("async function pollSensors()"):]
    assert "fetchRequest(" not in poll_section


def test_esp_bridge_rtos_sync_auth_and_observability():
    ino = _read(ESP_DIR / "esp_bridge.ino")
    uart_cpp = _read(ESP_DIR / "UartHandler.cpp")
    uart_h = _read(ESP_DIR / "UartHandler.h")
    state_h = _read(ESP_DIR / "RobotState.h")

    assert "uartSendLine" in uart_h and "s_uartTxMutex" in uart_cpp
    assert "s_responseQueue" in uart_cpp and "xQueueCreate" in uart_cpp
    assert "isValidJsonStart" not in uart_cpp
    assert "last_speech" not in state_h
    assert "uart_rx_errors" in state_h and "uart_overflows" in state_h
    assert "recordRxError()" in uart_cpp and "recordOverflow()" in uart_cpp

    setup_body = ino[ino.index("void setup()"):ino.index("void loop()")]
    assert setup_body.index("initUartTask()") < setup_body.index("setupWiFi()")
    assert setup_body.index("initLinkTask()") < setup_body.index("setupWiFi()")
    assert "g_responseBuffer" not in ino
    assert "g_wifiConnected" not in ino
    assert '"/state"' in ino
    assert "checkBridgeAuth" in ino
    assert 'ctx.hasArg("timeout")' in ino
    assert 'strcmp(doc["msg"].as<const char*>(), "hb")' in ino


def test_xmain_firmware_safety_and_nonblocking_invariants():
    xmain = _read(XMAIN_DIR / "xMain.ino")
    xcommands = _read(XMAIN_DIR / "app" / "xCommands.h")
    xrobot = _read(XMAIN_DIR / "xRobot.h")
    xservo = _read(XMAIN_DIR / "actuators" / "xServoBus.h")
    xstepper = _read(XMAIN_DIR / "actuators" / "xStepperPair.h")
    xds18 = _read(XMAIN_DIR / "peripherals" / "xDs18b20.h")
    xlcd = _read(XMAIN_DIR / "app" / "xLcdHub.h")
    xproto = _read(XMAIN_DIR / "xProtocol.h")
    xconfig = _read(XMAIN_DIR / "xConfig.h")

    # Watchdog + heartbeat boot ordering + estop latch/clear
    assert "<avr/wdt.h>" in xmain
    assert "wdt_disable()" in xmain and "wdt_enable(" in xmain and "wdt_reset()" in xmain
    assert "lastHeartbeatMs = millis();" in xmain
    assert "clearEstop()" in xrobot and "setEnable(false)" in xrobot
    assert "_estopped" in xservo
    assert 'cmd == F("estop_clear")' in xcommands

    # Ownership UID moved out of firmware; I2C errors reported
    assert "F3A186A5" not in xmain
    assert "isOwnerUid" not in xmain
    assert "i2c_errors" in xmain
    assert "i2c_errors" in xcommands

    # Non-blocking DS18B20 + shared emitNeopixelRequest + serial safety
    assert "setWaitForConversion(false)" in xds18
    assert "delay(200)" not in xds18
    assert "emitNeopixelRequest(" in xds18
    assert "SERIAL_IO.read()" not in xlcd
    assert "parseJsonStringAfter" in xproto

    # PROGMEM/RAM separation + IR hardware separation + pin guard
    assert "writePoseProgmem(" in xservo
    assert _extract_int_macro(xconfig, "IR_HW_ENABLED") == 0
    assert "#error" in xconfig and "!SERVO_USE_PCA9685" in xconfig

    # No old off-by-one substring offsets or blocking encoder loop in xCommands.h
    assert "substring(p+9)" not in xcommands
    assert "substring(p+15)" not in xcommands
    assert "home_timeout" in xcommands and "timeoutMs" in xstepper
    assert "startEncoderCalibration" in xcommands
    assert 'F("pid")' in xcommands or 'F("\\"pid\\":")' in xcommands
