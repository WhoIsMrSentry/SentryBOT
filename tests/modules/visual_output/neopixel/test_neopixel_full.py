from __future__ import annotations

from pathlib import Path
import sys
import types

from starlette.testclient import TestClient

from modules.visual_output.neopixel import cli
from modules.visual_output.neopixel.config_loader import load_config
from modules.visual_output.neopixel.emotions.loader import EmotionStore, get_shared_store
from modules.visual_output.neopixel.services.animations import (
    ANIMATIONS,
    eye_eyebrow,
    multi_color_gradient,
    rainbow_cycle,
    twinkle,
)
from modules.visual_output.neopixel.services.companion_leds import CompanionLedController
from modules.visual_output.neopixel.services.driver import NeoDriver, NeoDriverConfig, _SimStrip
from modules.visual_output.neopixel.services.runner import NeoRunner
from modules.visual_output.neopixel.xNeopixelService import create_app


def test_driver_backend_spi_khz_sim_rgb_and_power_budget(monkeypatch, caplog):
    # backend='sim' must not import pi5neo and must preserve true RGB order
    drv_sim = NeoDriver(NeoDriverConfig(num_leds=4, backend="sim", order="GRB", max_brightness=1.0, max_current_ma=0))
    assert drv_sim.backend_used == "sim"
    drv_sim.fill(10, 20, 30)
    assert isinstance(drv_sim._strip, _SimStrip)
    assert drv_sim._strip.buf[0] == (10, 20, 30)

    # Current limiter caps full white spikes cleanly
    drv_cap = NeoDriver(NeoDriverConfig(num_leds=23, backend="sim", max_brightness=1.0, max_current_ma=600))
    drv_cap.fill(255, 255, 255)
    pstat = drv_cap.power_status()
    assert pstat["last_estimated_ma"] <= 600.0
    assert 0.0 < drv_cap._strip.buf[0][0] < 255

    # backend='pi' uses ws2812_spi_khz=2400 and logs warning on fallback
    seen_spi = {}

    class _FakePi5Neo:
        def __init__(self, device, num_leds, spi_speed_khz):
            seen_spi["args"] = (device, num_leds, spi_speed_khz)
            self.anim = None

        def set_led_color(self, idx, r, g, b):
            pass

        def update_strip(self):
            pass

        def clear_strip(self):
            pass

        def animate(self, name, r, g, b, iterations, speed_ms):
            self.anim = (name, r, g, b)
            return True

    fake_mod = types.SimpleNamespace(Pi5Neo=_FakePi5Neo)
    monkeypatch.setitem(sys.modules, "pi5neo", fake_mod)
    drv_pi = NeoDriver(
        NeoDriverConfig(num_leds=5, backend="pi", speed_khz=800, ws2812_spi_khz=2400, order="GRB", max_brightness=1.0)
    )
    assert drv_pi.backend_used == "pi"
    assert seen_spi["args"] == ("/dev/spidev0.0", 5, 2400)
    assert drv_pi.animate("pulse", 10, 200, 30) is True
    # GRB order mapped on hardware animate call: (g, r, b) = (200, 10, 30)
    assert drv_pi._strip.anim == ("pulse", 200, 10, 30)


def test_emotion_store_shared_cache_reuses_palette():
    s1 = get_shared_store()
    s2 = get_shared_store()
    assert s1 is s2
    p1 = s1.load()
    p2 = EmotionStore().load()
    assert p1 is p2


def test_animations_and_runner_map_parity_and_empty_multi():
    cfg = NeoDriverConfig(num_leds=8, backend="sim", max_brightness=1.0, max_current_ma=0)
    runner = NeoRunner(cfg)
    try:
        # MULTI_* with empty colors returns False instead of silently True
        assert runner._dispatch_animation("MULTI_GRADIENT", runner.driver, [], None, None, 1) is False
        assert runner._dispatch_animation("M_WAVE", runner.driver, [], None, None, 1) is False
        # Zero-LED safety: no ZeroDivisionError or empty randrange
        empty_drv = _SimStrip(0)
        rainbow_cycle(empty_drv, iterations=1, wait=0)
        twinkle(empty_drv, (255, 0, 0), wait=0)
        multi_color_gradient(empty_drv, [(1, 2, 3)], iterations=1, wait=0)
        eye_eyebrow(empty_drv, (10, 20, 30), iterations=1, wait=0)
    finally:
        runner.stop()


def test_config_presets_drive_both_jewel_and_sticks():
    cfg = load_config()
    hw = cfg["hardware"]
    runner = NeoRunner(
        NeoDriverConfig(
            num_leds=int(hw["num_leds"]),
            backend="sim",
            max_brightness=1.0,
            max_current_ma=0,
        ),
        segments=hw["segments"],
        presets=cfg["presets"],
    )
    try:
        assert runner.apply_preset("emotion_neutral") is True
        runner._wait_for_animations()
        # Both stick_left (7..14) and stick_right (15..22) must be non-black from "stick" preset
        assert any(runner.driver._strip.buf[i] != (0, 0, 0) for i in range(7, 15))
        assert any(runner.driver._strip.buf[i] != (0, 0, 0) for i in range(15, 23))

        assert runner.fill_segment("stick", 12, 34, 56) is True
        assert runner.driver._strip.buf[7] == (12, 34, 56)
        assert runner.driver._strip.buf[22] == (12, 34, 56)
        assert runner.driver._strip.buf[0] == (0, 0, 0)
    finally:
        runner.stop()


def test_router_endpoints_and_lifespan_shutdown(tmp_path):
    cfg_path = tmp_path / "neo.yml"
    cfg_path.write_text(
        """
hardware:
  backend: sim
  num_leds: 23
  max_brightness: 1.0
  max_current_ma: 0
  segments:
    - { name: jewel, start: 0, count: 7 }
    - { name: stick_left, start: 7, count: 8 }
    - { name: stick_right, start: 15, count: 8 }
companion:
  enabled: true
  tick_ms: 10
  layout:
    jewel_start: 0
    jewel_count: 7
    sticks:
      - { name: left_brow, start: 7, count: 8, channel: 0 }
      - { name: right_brow, start: 15, count: 8, channel: 1, reverse: true }
  face:
    semantics:
      ambient_idle:
        animation: BREATHE
        duration_ms: 500
        frame:
          eye: { color: "#30E3CA", brightness: 0.5 }
          left_brow: { pose: neutral }
          right_brow: { pose: neutral }
presets:
  owner_welcome:
    jewel: { color: "#00AAFF" }
    stick: { color: "#104070" }
""",
        encoding="utf-8",
    )
    app = create_app(str(cfg_path))
    with TestClient(app) as client:
        h = client.get("/neopixel/healthz").json()
        assert h["ok"] is True
        assert h["power"]["backend"] == "sim"

        anims = client.get("/neopixel/animations").json()
        rec_names = {a["name"] for a in anims["animations"]}
        for expected in ("WIPE", "CHASE", "ALT", "BOUNCE", "RUN", "STACK", "EMOTIONAL_PULSE"):
            assert expected in rec_names
            assert expected in ANIMATIONS

        # Empty multi-color rejected cleanly
        bad_multi = client.post("/neopixel/animate", json={"name": "M_GRAD"})
        assert bad_multi.json()["ok"] is False

        # Valid animations & fills & emotes
        assert client.post("/neopixel/fill", params={"r_": 50, "g": 60, "b": 70}).json()["ok"] is True
        anim_res = client.post(
            "/neopixel/animate",
            json={"name": "EMOTIONAL_PULSE", "color": "20,40,60"},
        ).json()
        assert anim_res["ok"] is True
        em = client.post("/neopixel/emote", params={"emotion": "joy", "duration": 0.0}).json()
        assert em["ok"] is True
        assert em["chosen"][0]["rgb"] != [255, 255, 255]

        # Companion semantics & modes
        sem = client.post("/neopixel/companion/semantic", json={"semantic": "ambient_idle"}).json()
        assert sem["ok"] is True
        assert sem["status"]["active_semantic_animation"] == "BREATHE"

    assert not app.state.runner._animate_worker.is_alive()


def test_companion_static_dedup_listen_and_wake_chase_frames():
    drv = NeoDriver(NeoDriverConfig(num_leds=23, backend="sim", max_brightness=1.0, max_current_ma=0))
    shows = {"count": 0}
    orig_show = drv.show

    def _counting_show():
        shows["count"] += 1
        orig_show()

    drv.show = _counting_show  # type: ignore[method-assign]
    ctrl = CompanionLedController(
        drv,
        {
            "tick_ms": 10,
            "layout": {
                "jewel_start": 0,
                "jewel_count": 7,
                "jewel_center_index": 0,
                "sticks": [
                    {"name": "left_brow", "start": 7, "count": 8, "channel": 0},
                    {"name": "right_brow", "start": 15, "count": 8, "channel": 1, "reverse": True},
                ],
            },
        },
    )
    try:
        # Static frame with invalid pulse_hz falls back safely and deduplicates second draw
        ctrl.apply_face_frame({"eye": {"color": "#102030", "brightness": 1.0, "pulse_hz": "bad"}}, duration_ms=1000)
        shows_before = shows["count"]
        ctrl._render_face_frame()
        ctrl._render_face_frame()
        assert shows["count"] == shows_before + 1

        # Listen renders differently from eye
        ctrl.set_mode("eye")
        ctrl._render_eye_frame()
        eye_buf = list(drv._strip.buf)
        ctrl.set_mode("listen")
        ctrl._render_listen_frame()
        assert drv._strip.buf != eye_buf

        # wake_chase advances ring pixels across ticks
        ctrl.set_mode("wake_chase")
        ctrl._render_wake_chase_frame()
        f1 = list(drv._strip.buf)
        ctrl._render_wake_chase_frame()
        assert drv._strip.buf != f1
    finally:
        ctrl.stop()
    assert ctrl._thread is None


def test_cli_uses_config_and_keeps_fill_lit(monkeypatch):
    seen = {}

    class _DummyRunner:
        def __init__(self, cfg, segments=None):
            seen["cfg"] = cfg
            seen["segments"] = segments
            seen["cleared"] = None

        def fill(self, r, g, b):
            seen["fill"] = (r, g, b)
            return True

        def stop(self, *, clear=True):
            seen["cleared"] = clear

    monkeypatch.setattr(cli, "NeoRunner", _DummyRunner)
    assert cli.main(["fill", "10", "20", "30"]) == 0
    assert seen["cfg"].num_leds == 23
    assert seen["fill"] == (10, 20, 30)
    assert seen["cleared"] is False


def test_neo_ino_supports_segments_case_insensitive_clamp_and_abort():
    ino = Path("modules/visual_output/neopixel/tools/neo.ino").read_text(encoding="utf-8")
    assert "segmentRange(" in ino
    assert "shouldAbortAnimation()" in ino
    assert "delayOrAbort(" in ino
    assert "constrain(r, 0, 255)" in ino
    assert "EYE_EYEBROW" in ino
    assert "EMOTIONAL_PULSE" in ino
    assert "strcasecmp" in ino
