from __future__ import annotations

from unittest.mock import MagicMock
from modules.expression.animate.xAnimateService import xAnimateService


class FakeSerial:
    def __init__(self):
        self.sent = []

    def start(self):
        pass

    def stop(self):
        pass

    def set_pose(self, pose, duration_ms=None, source="autonomy"):
        self.sent.append({"cmd": "set_pose", "pose": pose, "duration_ms": duration_ms})

    def set_servo(self, index, deg, source="autonomy"):
        self.sent.append({"cmd": "set_servo", "index": index, "deg": deg})


def test_multimodal_animation_triggers_oled_and_neopixel(monkeypatch):
    serial = FakeSerial()
    svc = xAnimateService(serial=serial)

    fake_oled = MagicMock()
    fake_neo = MagicMock()
    fake_ears = MagicMock()

    svc.attach_oled(fake_oled)
    svc.attach_neopixel(fake_neo)
    svc.attach_ears(fake_ears)

    fake_anim = {
        "name": "multimodal_test",
        "loop": False,
        "steps": [
            {
                "pose": [90, 100, 80, 80],
                "duration_ms": 100,
                "face": "happy_eyes",
                "led": [0, 255, 0],
            }
        ],
    }

    monkeypatch.setattr(svc, "load", lambda name: fake_anim)

    res = svc.run("multimodal_test", loop=False)
    assert res is True
    assert len(serial.sent) == 1
    # Real OLED service surface: xAnimateService calls apply_manual() first
    # (xOledFacesService API); on_event/on_mode are legacy fallbacks.
    fake_oled.apply_manual.assert_called_with("animation", "happy_eyes")
    fake_neo.fill.assert_called_with(0, 255, 0)
    fake_ears.set_angles.assert_called_with(80.0, 80.0)


def test_multimodal_animation_led_string_uses_companion_set_mode():
    serial = FakeSerial()
    svc = xAnimateService(serial=serial)

    fake_oled = MagicMock()
    fake_neo = MagicMock()

    svc.attach_oled(fake_oled)
    svc.attach_neopixel(fake_neo)

    fake_anim = {
        "name": "led_string_test",
        "loop": False,
        "steps": [{"pose": [90, 90, 90, 90], "duration_ms": 10, "led": "thinking"}],
    }
    svc.load = lambda name: fake_anim  # type: ignore[assignment]

    assert svc.run("led_string_test", loop=False) is True
    # NeoRunner exposes companion_set_mode(), not set_mode (R27).
    fake_neo.companion_set_mode.assert_called_with("thinking")
