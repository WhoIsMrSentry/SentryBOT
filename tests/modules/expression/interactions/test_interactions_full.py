from __future__ import annotations

import os
from types import SimpleNamespace
import time

from starlette.testclient import TestClient

from modules.common.led_write_policy import LedWritePolicy
from modules.expression.interactions.config_loader import load_config
from modules.expression.interactions.services.adapters.neopixel_client import NeoHttpClient
from modules.expression.interactions.services.engine import InteractionEngine
from modules.expression.interactions.services.metrics import MetricsCollector
from modules.expression.interactions.services.rules import eval_condition, validate_rules_config
from modules.expression.interactions.xInteractionsService import create_app


def _offline_cfg(extra=None):
    cfg = {
        "tick_interval_ms": 50,
        "adapter": {"mode": "noop", "http_base_url": ""},
        "monitor": {"arduino": None},
        "output": {"via_expression": False},
        "defaults": {"brightness": 1.0, "idle": {"base": {"name": "BREATHE", "color": "#30E3CA"}}},
        "quiet_hours": {"enabled": False, "suppress_effects": True, "allow_events": ["error"]},
        "rules": [],
    }
    if extra:
        cfg.update(extra)
    return cfg


def test_rules_eval_rejects_unknown_keys_and_validates_config():
    assert eval_condition({}, {"metrics": {"cpu_temp": 90}}) is False
    assert eval_condition({"cpu_tempp_gte": 10}, {"metrics": {"cpu_temp": 90}}) is False
    assert eval_condition({"cpu_temp_gte": 75}, {"metrics": {"cpu_temp": 80}}) is True
    assert eval_condition(
        {"event": "speech.start", "quiet_hours_active": False},
        {"event": "speech.start", "quiet_hours_active": True},
    ) is False

    warnings = validate_rules_config([
        {
            "id": "bad_rule",
            "when": {"typo_key": True},
            "action": {},
            "priority": "bogus",
            "cooldown_ms": -5,
            "extra_field": 1,
        }
    ])
    joined = " | ".join(warnings)
    assert "unknown keys" in joined
    assert "unknown priority" in joined
    assert "unknown condition keys" in joined
    assert "empty or invalid 'action'" in joined
    assert "negative cooldown_ms" in joined


def test_config_loader_handles_bad_yaml_and_segments(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("rules: [unclosed", encoding="utf-8")
    cfg = load_config(config_path=str(bad))
    seg_names = [s["name"] for s in cfg["hardware"]["segments"]]
    assert seg_names == ["jewel", "stick_left", "stick_right"]


def test_metrics_collector_window_zero_temp_and_net_speed(monkeypatch):
    mc = MetricsCollector(window_s=60)
    monkeypatch.setattr(MetricsCollector, "_hardware_snapshot", staticmethod(lambda: None))
    monkeypatch.setattr(
        "modules.expression.interactions.services.metrics.psutil",
        SimpleNamespace(
            sensors_temperatures=lambda: {
                "nvme": [SimpleNamespace(current=42.0)],
                "cpu_thermal": [SimpleNamespace(current=0.0)],
            },
            cpu_percent=lambda interval=None: 50.0,
            net_io_counters=lambda: SimpleNamespace(bytes_recv=1_000_000, bytes_sent=0),
        ),
    )
    m1 = mc.sample()
    assert m1.cpu_temp == 0.0
    assert abs(m1.cpu_load - 0.5) < 1e-6
    assert m1.net_mbps == 0.0

    # Second sample with higher CPU load is averaged over window_s
    monkeypatch.setattr(
        "modules.expression.interactions.services.metrics.psutil",
        SimpleNamespace(
            sensors_temperatures=lambda: {"cpu_thermal": [SimpleNamespace(current=0.0)]},
            cpu_percent=lambda interval=None: 100.0,
            net_io_counters=lambda: SimpleNamespace(bytes_recv=2_000_000, bytes_sent=0),
        ),
    )
    m2 = mc.sample()
    assert abs(m2.cpu_load - 0.75) < 1e-6
    assert m2.net_mbps and m2.net_mbps > 0.0


def test_hardware_snapshot_returns_cpu_temp(monkeypatch):
    monkeypatch.setattr(os, "getloadavg", lambda: (1.5, 1.0, 0.5), raising=False)
    monkeypatch.setattr(MetricsCollector, "_read_cpu_temp", staticmethod(lambda: 54.2))
    snap = MetricsCollector._hardware_snapshot()
    assert snap == {"cpu_load_1m": 1.5, "cpu_temp_c": 54.2}


def test_neopixel_http_client_forwards_emotions_and_restores_idle(monkeypatch):
    posts = []

    class _FakeResp:
        status_code = 200

    def _fake_post(url, json=None, params=None, timeout=None):
        posts.append((url, json, params))
        return _FakeResp()

    monkeypatch.setattr(
        "modules.expression.interactions.services.adapters.neopixel_client.requests",
        SimpleNamespace(post=_fake_post),
    )
    client = NeoHttpClient("http://gw/neopixel", idle_base=("BREATHE", "#30E3CA"))
    client.play_effect("COMET", duration_ms=10, color="#112233", emotions=["joy"])
    assert len(posts) == 2
    assert posts[0][0].endswith("/animate")
    assert posts[0][1]["name"] == "COMET"
    assert posts[0][1]["emotions"] == ["joy"]
    assert (posts[0][1]["r"], posts[0][1]["g"], posts[0][1]["b"]) == (0x11, 0x22, 0x33)
    assert posts[1][0].endswith("/animate")
    assert posts[1][1]["name"] == "BREATHE"


def test_local_neo_adapter_forwards_emotions_and_respects_companion():
    calls = []

    class _Runner:
        def __init__(self):
            self.comp = False

        def companion_is_active(self):
            return self.comp

        def animate(self, name, **kwargs):
            calls.append((name, kwargs))

    runner = _Runner()
    eng = InteractionEngine(_offline_cfg(), neo_client=runner)
    eng.neo.play_effect("PULSE", duration_ms=30, color="#FF0000", emotions=["alert"])
    assert calls == [("PULSE", {"color": (255, 0, 0), "emotions": ["alert"]})]
    runner.comp = True
    eng.neo.play_effect("PULSE", duration_ms=30)
    assert len(calls) == 1


def test_via_expression_releases_lease_dedupes_base_and_forces_override():
    arb = LedWritePolicy({"channels": {"lights": {"default_lease_s": 5.0}}})
    cfg = _offline_cfg({
        "output": {"via_expression": True},
        "rules": [
            {
                "id": "cpu_hot",
                "when": {"cpu_temp_gte": 75},
                "action": {"base": {"name": "BREATHE", "color": "#FF0000"}},
                "priority": "high",
                "cooldown_ms": 5000,
            }
        ],
    })
    eng = InteractionEngine(cfg, expression_arbiter=arb)
    emitted = []
    eng.register_event_handler(lambda ev, data: emitted.append((ev, data)))
    eng.metrics.sample = lambda: SimpleNamespace(cpu_temp=80.0, cpu_load=0.2, net_mbps=0.0)  # type: ignore

    # Sustained condition emits base rule ONCE (not every tick)
    eng._tick()
    eng._tick()
    assert [e for e, _ in emitted] == ["interactions.cpu_hot"]

    # Non-forced manual effect claims lease and schedules automatic release
    assert eng.request_effect("COMET", duration_ms=30) == {"ok": True}
    assert arb.status()["lights_owner"] == "interactions"
    eng._tick()
    # Forced manual effect preempts active effect instead of being dropped
    assert eng.request_effect("METEOR", duration_ms=25, force=True) == {"ok": True}
    eng._tick()
    assert [e for e, _ in emitted if e == "interactions.effect"][-1] == "interactions.effect"
    time.sleep(0.08)
    assert arb.status()["lights_owner"] == ""
    eng.stop()


def test_claim_lights_fails_closed_on_arbiter_error():
    class _BrokenArbiter:
        def claim_lights(self, *args, **kwargs):
            raise RuntimeError("arbiter down")

    eng = InteractionEngine(_offline_cfg(), expression_arbiter=_BrokenArbiter())
    assert eng._claim_lights_for_event("test.evt") is False


def test_arduino_health_monitor_resolves_gateway_and_logs(monkeypatch, caplog):
    seen_urls = []
    monkeypatch.setenv("SENTRY_GATEWAY_URL", "http://127.0.0.1:18080")
    monkeypatch.setattr(
        "modules.expression.interactions.services.engine_guards.requests",
        SimpleNamespace(get=lambda url, timeout=0.5: (seen_urls.append(url), SimpleNamespace(status_code=503))[1]),
    )
    eng = InteractionEngine(
        _offline_cfg({"monitor": {"arduino": {"url": "@gateway/arduino/healthz", "interval_s": 0.1}}})
    )
    with caplog.at_level("WARNING", logger="interactions.engine_guards"):
        eng._update_arduino_state(time.time())
    assert seen_urls == ["http://127.0.0.1:18080/arduino/healthz"]
    assert eng.get_state()["ctx"]["arduino_connected"] is False
    assert any("Arduino health probe failed" in rec.message for rec in caplog.records)


def test_interactions_router_validation_guards_and_rules_trace(tmp_path):
    cfg_file = tmp_path / "interactions.yml"
    cfg_file.write_text(
        """
adapter:
  mode: noop
  http_base_url: ""
monitor:
  arduino: null
output:
  via_expression: false
quiet_hours:
  enabled: true
  start: "00:00"
  end: "23:59"
  suppress_effects: true
  allow_events: ["error"]
rules:
  - id: bad_rule
    when: { unknown_cond: 1 }
    action: { base: { name: BREATHE } }
    priority: medium
    cooldown_ms: 500
""",
        encoding="utf-8",
    )
    app = create_app(str(cfg_file))
    with TestClient(app) as client:
        assert app.state.engine._thread is not None

        # Invalid duration_ms -> 422 instead of 500 ValueError
        bad_res = client.post("/interactions/effect", json={"name": "COMET", "duration_ms": "abc"})
        assert bad_res.status_code == 422

        # Quiet hours rejects non-forced effect/base loudly
        eff_res = client.post("/interactions/effect", json={"name": "COMET", "duration_ms": 100})
        assert eff_res.status_code == 200
        assert eff_res.json() == {"ok": False, "reason": "quiet_hours"}

        base_res = client.post("/interactions/base", json={"name": "PULSE", "color": "#FF0000"})
        assert base_res.status_code == 200
        assert base_res.json() == {"ok": False, "reason": "quiet_hours"}

        # Forced effect succeeds & GET /rules/trace reports quiet hours + config warning
        ok_eff = client.post("/interactions/effect", json={"name": "COMET", "duration_ms": 50, "force": True})
        assert ok_eff.json()["ok"] is True

        trace = client.get("/interactions/rules/trace")
        assert trace.status_code == 200
        body = trace.json()
        assert body["ok"] is True
        assert body["quiet_hours"]["active"] is True
        assert any("unknown condition keys" in w for w in body["config_warnings"])
        assert len(body["rules"]) == 1
        assert body["rules"][0]["id"] == "bad_rule"

    # Lifespan exit stops engine thread cleanly
    assert app.state.engine._thread is None
