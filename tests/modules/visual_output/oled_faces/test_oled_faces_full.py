"""Comprehensive unit and router tests for oled_faces (driver optimization, burn-in, arbiter, API)."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

pytest.importorskip("PIL")

from PIL import Image, ImageDraw

from modules.visual_output.oled_faces.api.router import get_router
from modules.visual_output.oled_faces.config_loader import load_config
from modules.visual_output.oled_faces.services.eyes.activity_drawings import _deploying
from modules.visual_output.oled_faces.services.eyes.engine import EyeEngine
from modules.visual_output.oled_faces.services.eyes.vibes import render_vibe
from modules.visual_output.oled_faces.services.face_renderer import FaceRenderer
from modules.visual_output.oled_faces.services.mapper import FaceMapper, OledAction
from modules.visual_output.oled_faces.services.pi_ssd1306_driver import PiSsd1306Driver
from modules.visual_output.oled_faces.xOledFacesService import xOledFacesService


class _FakeSMBus:
    def __init__(self, fail_on_write: bool = False):
        self.cmds: list[int] = []
        self.data_writes: int = 0
        self.closed: bool = False
        self.fail_on_write = fail_on_write

    def write_byte_data(self, addr: int, reg: int, val: int) -> None:
        if self.fail_on_write:
            raise OSError("I2C NACK")
        if reg == 0x00:
            self.cmds.append(val)

    def write_i2c_block_data(self, addr: int, reg: int, chunk: list[int]) -> None:
        if self.fail_on_write:
            raise OSError("I2C block write failed")
        if reg == 0x40:
            self.data_writes += 1

    def close(self) -> None:
        self.closed = True


def _make_bus_driver(monkeypatch, bus_obj: _FakeSMBus, **extra_cfg) -> PiSsd1306Driver:
    fake_mod = SimpleNamespace(SMBus=lambda bus_id: bus_obj)
    monkeypatch.setitem(__import__("sys").modules, "smbus2", fake_mod)
    cfg = {"enabled": True, "contrast": 143, **extra_cfg}
    return PiSsd1306Driver(cfg)


def test_pil_to_buffer_exact_bit_order():
    d = PiSsd1306Driver({"enabled": False})
    img = Image.new("1", (128, 64), 0)
    px = img.load()
    pts = [(0, 0), (10, 5), (127, 63)]
    for x, y in pts:
        px[x, y] = 1
    d._pil_to_buffer(img)

    for x, y in pts:
        idx = x + (y // 8) * 128
        bit = 1 << (y & 7)
        assert d._buffer[idx] & bit
    assert d._buffer[10] == (1 << 5)


def test_dirty_page_delta_writes_and_zero_write_on_identical_frame(monkeypatch):
    bus = _FakeSMBus()
    d = _make_bus_driver(monkeypatch, bus)
    assert d.begin() is True

    # Reset counters after init clear+flush (8 pages)
    bus.cmds.clear()
    bus.data_writes = 0

    img = Image.new("1", (128, 64), 0)
    d.show_pil_image(img)  # matches cleared buffer -> 0 dirty pages
    assert d.status()["dirty_pages_last"] == 0
    assert bus.data_writes == 0

    # Set pixel on y=25 -> page 3 only (25 // 8 == 3)
    img.load()[20, 25] = 1
    d.show_pil_image(img)
    assert d.status()["dirty_pages_last"] == 1
    assert bus.data_writes == 8  # 1 page * 128 bytes / 16 bytes/chunk
    assert 0xB3 in bus.cmds  # page 3 command only


def test_burn_in_dim_and_sleep_and_wake(monkeypatch):
    bus = _FakeSMBus()
    now_val = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now_val[0])

    d = _make_bus_driver(
        monkeypatch,
        bus,
        dim_contrast=16,
        burn_in_dim_s=10.0,
        burn_in_sleep_s=20.0,
    )
    assert d.begin() is True
    bus.cmds.clear()

    blank = Image.new("1", (128, 64), 0)
    now_val[0] = 111.0  # > burn_in_dim_s
    d.show_pil_image(blank)
    st = d.status()
    assert st["dimmed"] is True
    assert st["sleeping"] is False
    assert st["contrast"] == 16

    now_val[0] = 122.0  # > burn_in_sleep_s
    d.show_pil_image(blank)
    assert d.status()["sleeping"] is True
    assert 0xAE in bus.cmds

    # Changed frame wakes panel (0xAF) and restores contrast (143)
    bus.cmds.clear()
    active = Image.new("1", (128, 64), 0)
    active.load()[1, 1] = 1
    now_val[0] = 123.0
    d.show_pil_image(active)
    st = d.status()
    assert st["sleeping"] is False
    assert st["dimmed"] is False
    assert st["contrast"] == 143
    assert 0xAF in bus.cmds


def test_i2c_error_reconnect_backoff_and_begin_closes_old_bus(monkeypatch):
    bus1 = _FakeSMBus()
    now_val = [10.0]
    monkeypatch.setattr(time, "monotonic", lambda: now_val[0])
    d = _make_bus_driver(monkeypatch, bus1)
    assert d.begin() is True

    # Calling begin again closes old bus first
    bus2 = _FakeSMBus()
    monkeypatch.setitem(__import__("sys").modules, "smbus2", SimpleNamespace(SMBus=lambda _: bus2))
    assert d.begin() is True
    assert bus1.closed is True

    # Trigger write error -> _ok=False and bus closed
    bus2.fail_on_write = True
    img = Image.new("1", (128, 64), 1)
    d.show_pil_image(img)
    assert d.status()["ok"] is False
    assert d.status()["i2c_errors"] >= 1
    assert bus2.closed is True

    # Reconnect succeeds once backoff expires and fresh bus works
    bus3 = _FakeSMBus()
    monkeypatch.setitem(__import__("sys").modules, "smbus2", SimpleNamespace(SMBus=lambda _: bus3))
    now_val[0] += 5.0
    d.show_pil_image(img)
    st = d.status()
    assert st["ok"] is True
    assert st["reconnect_count"] == 1


def test_face_renderer_preserves_contrast_when_brightness_omitted():
    with pytest.MonkeyPatch.context() as mp:
        driver = MagicMock()
        driver.begin.return_value = True
        driver.width = 128
        driver.height = 64
        driver.contrast = 143
        mp.setattr(
            "modules.visual_output.oled_faces.services.face_renderer.PiSsd1306Driver",
            lambda cfg: driver,
        )
        renderer = FaceRenderer({"contrast": 143, "fps": 20})
        assert renderer.begin() is True
        try:
            eng = renderer._engine
            eng.stop()
            eng._blink = None
            # First step in neutral mood must NOT clobber panel contrast with 255
            eng._step(time.monotonic(), 0.04)
            driver.set_brightness.assert_not_called()
            # Standby mood dims brightness (1), then neutral restores initial contrast (143)
            eng.set_mood("standby")
            eng._step(time.monotonic() + 0.01, 0.04)
            assert driver.set_brightness.call_args.args[0] == 1
            eng._blink = None
            eng.set_mood("neutral")
            eng._step(time.monotonic() + 0.02, 0.04)
            assert driver.set_brightness.call_args.args[0] == 143
        finally:
            renderer.close()


def test_vibe_state_isolated_and_deploying_scratch_reused():
    img1 = Image.new("1", (128, 64), 0)
    img2 = Image.new("1", (128, 64), 0)
    eng1 = EyeEngine(lambda _: None)
    eng2 = EyeEngine(lambda _: None)
    render_vibe("game_of_life", ImageDraw.Draw(img1), 128, 64, 1.0, state=eng1._vibe_state)
    # eng2's generation clock should still be 0.0 (unmutated by eng1)
    assert eng2._vibe_state.life_gen == 0.0
    render_vibe("game_of_life", ImageDraw.Draw(img2), 128, 64, 1.0, state=eng2._vibe_state)
    assert eng2._vibe_state.life_gen == 1.0

    # _deploying draws smoothly onto existing PIL buffer across multiple calls
    d = ImageDraw.Draw(img1)
    _deploying(d, 128, 64, 1.0)
    _deploying(d, 128, 64, 1.5)
    assert img1.getbbox() is not None


def test_router_validation_stt_clear_and_status_honesty(monkeypatch):
    cfg = load_config(overrides={"display": {"enabled": False, "contrast": 99}})
    assert cfg["display"]["contrast"] == 99
    assert cfg["display"]["width"] == 128  # deep merge preserved nested defaults
    assert not hasattr(FaceMapper(cfg), "from_arduino_event")

    svc = xOledFacesService(cfg=cfg)
    eng = EyeEngine(lambda _: None)
    svc.display._engine = eng

    app = FastAPI()
    app.include_router(get_router(svc))
    client = TestClient(app)

    # Honest status: display disabled -> ok False
    st = client.get("/oled_faces/status").json()
    assert st["ok"] is False
    assert st["has_display"] is False

    # STT text set + explicit empty clear
    resp = client.post("/oled_faces/stt_text", json={"text": "Merhaba Sentry", "duration_s": 5.0})
    assert resp.status_code == 200 and resp.json()["cleared"] is False
    assert eng._subtitle_text == "Merhaba Sentry"

    resp_clear = client.post("/oled_faces/stt_text", json={"text": ""})
    assert resp_clear.status_code == 200 and resp_clear.json()["cleared"] is True
    assert eng._subtitle_text is None

    # Invalid Pydantic inputs rejected with 422
    assert client.post("/oled_faces/stt_text", json={"text": "x", "duration_s": -2}).status_code == 422
    assert client.post("/oled_faces/manual", json={"mode": "bogus", "name": "happy"}).status_code == 422
    assert client.post("/oled_faces/event", json={"type": "   "}).status_code == 422

    # stt_text returns 503 when engine absent
    svc.display._engine = None
    assert client.post("/oled_faces/stt_text", json={"text": "hi"}).status_code == 503


def test_stt_event_early_return_and_arbiter_deny_release():
    cfg = load_config(overrides={"display": {"enabled": False}})
    arbiter = MagicMock()
    arbiter.claim_oled.return_value = True
    svc = xOledFacesService(cfg=cfg, expression_arbiter=arbiter)
    eng = EyeEngine(lambda _: None)
    svc.display._engine = eng
    svc.display.apply = MagicMock(return_value=True)

    # Apply initial mood so _last_sent is populated
    assert svc._apply(OledAction("animation", "listening"), priority=80, force=True) is True
    before = svc._last_sent

    # speech.final updates subtitle and does NOT overwrite _last_sent with normal/fallback
    svc.on_interaction_event("speech.final", {"text": "Test komutu"})
    assert eng._subtitle_text == "Test komutu"
    assert svc._last_sent == before

    # Arbiter error fails closed without calling display.apply
    svc.display.apply.reset_mock()
    arbiter.claim_oled.side_effect = RuntimeError("arbiter down")
    assert svc._apply(OledAction("bitmap", "happy"), priority=80, force=True) is False
    svc.display.apply.assert_not_called()

    # If claim_oled succeeds but display.apply fails, release("oled_faces") cleans lease
    arbiter.claim_oled.side_effect = None
    arbiter.claim_oled.return_value = True
    svc.display.apply.return_value = False
    assert svc._apply(OledAction("bitmap", "sad"), priority=80, force=True) is False
    arbiter.release.assert_called_once_with("oled_faces")
