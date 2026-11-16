from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from starlette.testclient import TestClient

from modules.common.emotion_vocab import Emotion
from modules.expression.semantic.api.router import ExpressRequest, get_router
from modules.expression.semantic.config_loader import DEFAULT_CONFIG, load_config
from modules.expression.semantic.services.adapters import (
    HeadAdapter,
    NeopixelAdapter,
    OledAdapter,
    PiServoAdapter,
    SpeakAdapter,
)
from modules.expression.semantic.services.arbitrator import ExpressionArbiter, ModalityClients
from modules.expression.semantic.services.state import SemanticExpressionEngine
from modules.expression.semantic.xExpressionService import create_app


class _FakeAsyncClient:
    def __init__(self, fail_paths=None):
        self.calls = []
        self.fail_paths = set(fail_paths or ())

    async def post(self, path, json=None, params=None):
        self.calls.append((path, json, params))
        status = 500 if path in self.fail_paths else 200
        return SimpleNamespace(status_code=status)


def test_semantic_config_loader_fallback_and_overrides(tmp_path):
    broken = tmp_path / "broken.yml"
    broken.write_text("state: [bad", encoding="utf-8")
    cfg = load_config(config_path=str(broken), overrides={"state": {"max_history": 42}})
    assert cfg["state"]["max_history"] == 42
    assert cfg["server"]["port"] == DEFAULT_CONFIG["server"]["port"]


def test_modality_adapters_contracts(monkeypatch):
    async def run():
        fake_neo_client = _FakeAsyncClient()
        monkeypatch.setattr(
            "modules.expression.semantic.services.adapters.neopixel_adapter.get_http_client",
            lambda *_: fake_neo_client,
        )
        neo = NeopixelAdapter("http://gw:8080")
        assert await neo.set_effect("METEOR", (10, 20, 30), speed=1.5, duration_s=4.0) is True
        assert fake_neo_client.calls[0][0] == "/neopixel/animate"
        assert fake_neo_client.calls[0][1]["name"] == "METEOR"
        assert await neo.set_color((123, 45, 67)) is True
        assert fake_neo_client.calls[1][0] == "/neopixel/fill"
        assert fake_neo_client.calls[1][2] == {"r_": 123, "g": 45, "b": 67}
        assert await neo.turn_off() is True
        assert fake_neo_client.calls[2][0] == "/neopixel/clear"

        fake_oled_client = _FakeAsyncClient()
        monkeypatch.setattr(
            "modules.expression.semantic.services.adapters.oled_adapter.get_http_client",
            lambda *_: fake_oled_client,
        )
        oled = OledAdapter("http://gw:8080")
        assert await oled.play_animation("happy", duration_s=6.5, loop=True) is True
        assert fake_oled_client.calls[0] == (
            "/oled_faces/manual",
            {"mode": "animation", "name": "happy", "duration_s": 6.5, "loop": True},
            None,
        )

        fake_speak_client = _FakeAsyncClient()
        monkeypatch.setattr(
            "modules.expression.semantic.services.adapters.speak_adapter.get_http_client",
            lambda *_: fake_speak_client,
        )
        speak = SpeakAdapter("http://gw:8080")
        assert await speak.say("Merhaba", tone="joy", language="tr", pitch_shift=0.1, speed=1.1) is True
        assert fake_speak_client.calls[0][0] == "/speak/say"

        fake_head_client = _FakeAsyncClient()
        monkeypatch.setattr(
            "modules.expression.semantic.services.adapters.head_adapter.get_http_client",
            lambda *_: fake_head_client,
        )
        head = HeadAdapter("http://gw:8080")
        # Out-of-bounds angles clamped cleanly (pan 30..150, tilt 60..120)
        assert await head.move_head(10, 140) is True
        pan_call, tilt_call = fake_head_client.calls[0], fake_head_client.calls[1]
        assert pan_call[1] == {"cmd": "set_servo", "index": 0, "deg": 30.0}
        assert tilt_call[1] == {"cmd": "set_servo", "index": 1, "deg": 120.0}

        ears = PiServoAdapter("http://gw:8080")
        assert await ears.set_ears("happy") is True
        assert fake_head_client.calls[2][0] == "/piservo/emotion"

    asyncio.run(run())


def test_arbitrator_transition_graph_complete_fear_lock_and_hardware_reset():
    async def run():
        events = []

        class _SlowHead:
            async def move_head(self, pan, tilt):
                events.append(("head", pan, tilt))
                return True

        class _FakeNeo:
            async def set_effect(self, effect, color, speed=1.0, duration_s=3.0):
                events.append(("leds_effect", effect))
                await asyncio.sleep(0.5)
                return True

            async def turn_off(self):
                events.append(("leds_off",))
                return True

        class _FakeEars:
            async def set_ears(self, position="neutral"):
                events.append(("ears", position))
                return True

        arb = ExpressionArbiter(
            ModalityClients(neopixel=_FakeNeo(), head=_SlowHead(), piservo=_FakeEars())
        )
        # All 29 canonical Emotion enum members exist in transition graph
        assert set(Emotion).issubset(set(arb._visual_transition_graph.keys()))

        # Joy locks visuals; ANGER without force must be blocked by visual lock
        r1 = await arb.express_emotion("joy", duration_s=1.0, modalities=["leds", "head", "ears"], force=True)
        assert r1["ok"] is True
        await asyncio.sleep(0.02)
        r_blocked = await arb.express_emotion("anger", duration_s=1.0, modalities=["leds"], force=False)
        assert r_blocked["ok"] is False
        assert r_blocked["reason"] in {"rate_limited", "visual_locked"}

        # Emergency keyword ("alarm") still preempts, cancels previous task, and resets hardware
        r_alarm = await arb.express_emotion("alarm", duration_s=0.1, modalities=["leds"])
        assert r_alarm["ok"] is True
        assert ("leds_off",) in events
        assert ("head", 90, 90) in events
        assert ("ears", "neutral") in events

        # Preview dry-run evaluates guards without executing adapters or changing visual lock
        prev = await arb.preview_emotion("joy", intensity=1.2, modalities=["leds", "head", "ears"], force=False)
        assert prev["dry_run"] is True
        assert prev["would_execute"] is False
        assert "head_target" in prev
        assert 60 <= prev["head_target"]["tilt"] <= 120

        await arb.stop()

    asyncio.run(run())


def test_semantic_state_supports_canonical_vocab_and_camera_mapping():
    eng = SemanticExpressionEngine()
    assert eng.get_state()["targets"]["led"]["mode"] == "breathe"

    out = eng.apply({"emotion": "anger", "attention": "camera"})
    assert out["state"]["emotion"] == "anger"
    assert out["targets"]["led"]["mode"] == "eye"
    assert out["targets"]["led"]["color"] != "#4060ff"

    out_tr = eng.apply({"emotion": "korkmuş"})
    assert out_tr["state"]["emotion"] == "fear"
    assert out_tr["targets"]["oled"]["mood"] != "neutral"

    # ExpressRequest default includes ears
    req = ExpressRequest(emotion="joy")
    assert "ears" in req.modalities


def test_semantic_router_503_express_preview_and_create_app_config(tmp_path):
    # Router without arbiter returns HTTP 503 on express & preview
    bare_app = FastAPI()
    bare_app.include_router(get_router(SemanticExpressionEngine()))
    with TestClient(bare_app) as c:
        assert c.post("/expression/express", json={"emotion": "joy"}).status_code == 503
        assert c.post("/expression/preview", json={"emotion": "joy"}).status_code == 503

    # create_app propagates config_path and mounts router + arbiter eagerly
    cfg_file = tmp_path / "semantic.yml"
    cfg_file.write_text(
        """
state:
  default_emotion: curious
adapters:
  enabled: false
output_bridge:
  enabled: false
""",
        encoding="utf-8",
    )
    app = create_app(str(cfg_file))
    with TestClient(app) as client:
        st = client.get("/expression/status")
        assert st.status_code == 200
        assert st.json()["engine"]["emotion"] == "curious"
        assert "arbiter" in st.json()

        prev = client.post("/expression/preview", json={"emotion": "pride", "intensity": 1.4})
        assert prev.status_code == 200
        pbody = prev.json()
        assert pbody["dry_run"] is True
        assert pbody["emotion"] == "pride"
        assert pbody["would_execute"] is True

        # Preview must NOT have created a visual lock, so express executes right away
        exp = client.post("/expression/express", json={"emotion": "pride", "duration_s": 0.5})
        assert exp.status_code == 200
        assert exp.json()["ok"] is True
