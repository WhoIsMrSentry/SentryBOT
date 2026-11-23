from __future__ import annotations

import json
from pathlib import Path

from modules.arduino_serial.contract import build_lcd_cmd, validate_arduino_payload


REPO_ROOT = Path(__file__).resolve().parents[3]
XCOMMANDS_H = REPO_ROOT / "arduino" / "firmware" / "xMain" / "app" / "xCommands.h"


def test_build_lcd_cmd_supports_20x4_overlay_and_restore():
    legacy = build_lcd_cmd(top="Merhaba", bottom="Dunya")
    assert legacy == {"cmd": "lcd", "top": "Merhaba", "bottom": "Dunya"}
    assert validate_arduino_payload(legacy) is None

    four_line = build_lcd_cmd(
        l1="12345678901234567890",
        l2="kinci satir burada",
        l3="Ucuncu satir metni",
        l4="Dorduncu satir",
        overlay=True,
    )
    assert four_line == {
        "cmd": "lcd",
        "l1": "12345678901234567890",
        "l2": "kinci satir burada",
        "l3": "Ucuncu satir metni",
        "l4": "Dorduncu satir",
        "overlay": True,
    }
    assert validate_arduino_payload(four_line) is None
    assert len(json.dumps(four_line, separators=(",", ":"))) < 256

    restore = build_lcd_cmd(overlay=True, restore=True)
    assert restore == {"cmd": "lcd", "overlay": True, "restore": True}
    assert validate_arduino_payload(restore) is None


def test_lcd_validator_rejects_invalid_fields():
    assert validate_arduino_payload({"cmd": "lcd"}) is not None
    assert validate_arduino_payload({"cmd": "lcd", "overlay": "yes", "l1": "abc"}) is not None
    assert validate_arduino_payload({"cmd": "lcd", "restore": "no"}) is not None
    assert validate_arduino_payload({"cmd": "lcd", "l3": 123}) is not None


def test_firmware_lcd_handler_preserves_menu_and_supports_4_lines():
    src = XCOMMANDS_H.read_text(encoding="utf-8")
    for token in (
        'F("\\"overlay\\":")',
        'F("\\"restore\\":")',
        'F("\\"l1\\":")',
        'F("\\"l4\\":")',
        "g_lcdStatus.isPinned()",
        "g_lcdStatus.show4To(tgt, l1, l2, l3, l4, true)",
        "g_irMenu.showHome()",
    ):
        assert token in src, f"Missing expected firmware LCD token: {token}"
