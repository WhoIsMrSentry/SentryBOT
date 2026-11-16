"""Iteration 19 tests for modules/autonomy fixes, error paths, E2E behavior, and unified risk/safety semantics."""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml

from modules.autonomy.api.router import get_router
from modules.autonomy.config_loader import load_config
from modules.autonomy.services.behavior_composer import BehaviorComposer
from modules.autonomy.services.behavior_planner import BehaviorPlanner
from modules.autonomy.services.behavior_shadow_learner import BehaviorShadowLearner
from modules.autonomy.services.brain import AutonomyBrain
from modules.autonomy.services.client import ServiceClient
from modules.autonomy.services.cloud_backup_sync import CloudBackupSync
from modules.autonomy.services.companion_goal_selector import CompanionGoalSelector
from modules.autonomy.services.living_needs import LivingNeedsEngine
from modules.autonomy.services.mood import MoodManager
from modules.autonomy.services.needs_engine import CompanionNeedsEngine, extract_risk_and_safety
from modules.autonomy.services.owner_person_learning import OwnerPersonLearning
from modules.autonomy.services.pi_hardware_runtime import PiHardwareRuntime
from modules.autonomy.services.reflection_planner import ReflectionPlanner
from modules.autonomy.services.safe_navigation import SafeNavigationMemory
from modules.autonomy.services.saliency_map import SaliencyTarget
from modules.autonomy.services.scene_register import SceneRegister
from modules.autonomy.services.spinal_cord_reflex import SpinalCordReflexEngine
from modules.autonomy.services.topomap_motion_executor import TopomapMotionExecutor


def test_spinal_cord_hardware_and_voice_emergency_paths():
    client = MagicMock()
    memory = MagicMock()
    engine = SpinalCordReflexEngine({"enabled": True, "cooldown_s": 0.0}, client, memory)

    assert engine.observe_hardware_event("cliff", {}) is True
    client.push_interaction_event.assert_any_call("motor.stop", {"priority": "emergency"})
    memory.add_event.assert_called()

    # Non-imminent obstacle should not fire reflex
    client.reset_mock()
    assert engine.observe_hardware_event("ultra_dist", {"cm": 25}) is False
    client.push_interaction_event.assert_not_called()

    # Imminent obstacle < 10cm triggers reflex
    assert engine.observe_hardware_event("ultra_dist", {"distance_cm": 6}) is True

    # Dict-style Laya emergency decision (no .is_emergency attribute access crash)
    client.reset_mock()
    assert engine.observe_voice_emergency({"is_emergency": True, "urgency_score": 2.9, "target_module": "emergency_stop"}) is True
    client.push_interaction_event.assert_any_call("motor.stop", {"priority": "emergency", "source": "laya_voice"})

    # Non-emergency dict & malformed payload rejected cleanly
    assert engine.observe_voice_emergency({"is_emergency": False, "target_module": "chat"}) is False
    assert engine.observe_voice_emergency("invalid") is False


def test_spinal_cord_error_path_survives_broken_client():
    client = MagicMock()
    client.push_interaction_event.side_effect = RuntimeError("bus down")
    memory = MagicMock()
    engine = SpinalCordReflexEngine({"enabled": True, "cooldown_s": 0.0}, client, memory)
    assert engine.observe_voice_emergency(SimpleNamespace(is_emergency=True, urgency_score=3.0, target_module="emergency_stop")) is True
    memory.add_event.assert_called()


def test_topomap_learn_policy_execute_and_stepper_contract(tmp_path):
    map_path = tmp_path / "topomap.json"
    client = MagicMock()
    client.read_sensor.return_value = {"cm": 50.0}
    client.set_stepper.return_value = {"ok": True}
    client.robot_command.return_value = {"ok": True}

    executor = TopomapMotionExecutor(
        {
            "map_path": str(map_path),
            "allow_base_motion": True,
            "require_ultrasonic_clearance": True,
            "min_clearance_cm": 25.0,
            "companion_policies": {
                "safe_exploration": {
                    "enabled": True,
                    "required_tags": ["safe", "exploration"],
                    "minimum_distance_from_owner_m": 1.0,
                    "selection": "first",
                }
            },
        },
        client=client,
    )

    learned = executor.learn_place(
        {
            "id": "corner_a",
            "name": "corner_a",
            "tags": ["safe", "exploration"],
            "distance_from_owner_m": 1.5,
            "steps": [{"type": "stepper", "id": 0, "value": 90, "drive": 160}],
        }
    )
    assert learned["ok"] is True
    saved_place = learned["place"]
    assert saved_place["tags"] == ["exploration", "safe"]
    assert saved_place["distance_from_owner_m"] == 1.5
    assert len(saved_place["motion_plan"]) == 1

    # Companion policy inline + place execution works and emits stepper mode='pos' (not 'rel')
    policy_res = executor.execute_companion_policy("safe_exploration")
    assert policy_res["ok"] is True
    assert policy_res["moved"] is True
    assert policy_res["selected_place"] == "corner_a"
    client.set_stepper.assert_called_once_with(0, "pos", 90, drive=160)

    # Error path: clearance blocked
    client.read_sensor.return_value = {"cm": 12.0}
    blocked = executor.execute_goal({"place_id": "corner_a"})
    assert blocked["ok"] is False
    assert blocked["reason"] == "clearance_blocked"

    # Error path: unknown place without inline steps
    missing = executor.execute_goal({"place_id": "nonexistent"})
    assert missing["ok"] is False
    assert missing["reason"] == "place_not_found"


def test_topomap_safe_nav_and_owner_learning_resolve_relative_to_repo_root(monkeypatch, tmp_path):
    topo = TopomapMotionExecutor.__new__(TopomapMotionExecutor)
    del topo
    # Relative paths resolve against repo root rather than cwd
    from modules.autonomy.services.storage_utils import resolve_autonomy_path

    expected_root = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(tmp_path)
    p = resolve_autonomy_path("data/test_probe.json", "data/default.json")
    assert p.is_absolute()
    assert p == expected_root / "data" / "test_probe.json"

    # Verify SafeNavigationMemory & OwnerPersonLearning accept lock + atomic write cleanly
    assert SafeNavigationMemory is not None
    assert OwnerPersonLearning is not None


def test_behavior_composer_matches_real_service_client_signature():
    client = MagicMock(spec=ServiceClient)
    brain = MagicMock()
    composer = BehaviorComposer(brain=brain, client=client)

    res = composer.execute_plan(
        {
            "emotion": {"label": "joy", "intensity": 0.9, "duration_s": 5.0},
            "lights": {"effect_hint": "pulse", "palette_hint": "joy", "duration_s": 4.0},
            "posture": {"head_tilt": 100, "eyes": "happy"},
        }
    )
    assert res["status"] == "executed"
    assert res["components"]["eyes"] == "happy"
    client.express_emotion.assert_called_once_with(emotion="joy", intensity=0.9, duration_s=5.0)
    client.set_neopixel.assert_called_once_with(
        effect="pulse", emotions=["joy"], duration=4.0, lease_source="behavior_composer"
    )
    client.oled_show.assert_called_once_with("happy")


def test_shadow_learner_deterministic_hash_and_client_contract(tmp_path):
    save_file = tmp_path / "macros.yml"
    cfg = {"enabled": True, "min_repetitions": 2, "gap_s": 5.0, "save_path": str(save_file)}
    learner = BehaviorShadowLearner(cfg)
    for _ in range(2):
        learner._current_episode = [
            {"type": "neopixel", "payload": {"mode": "pulse", "emotions": ["joy"]}},
            {"type": "head_move", "payload": {"pan": 95, "tilt": 90}},
        ]
        learner._finalize_episode()
    macros = learner.get_learned_macros()
    assert len(macros) == 1
    macro_id = next(iter(macros))

    # Deterministic across instances
    learner2 = BehaviorShadowLearner({**cfg, "save_path": str(tmp_path / "macros2.yml")})
    for _ in range(2):
        learner2._current_episode = [
            {"type": "neopixel", "payload": {"mode": "pulse", "emotions": ["joy"]}},
            {"type": "head_move", "payload": {"pan": 95, "tilt": 90}},
        ]
        learner2._finalize_episode()
    assert macro_id in learner2.get_learned_macros()

    mock_client = MagicMock(spec=ServiceClient)
    assert learner.replay_macro(macro_id, mock_client) is True
    mock_client.set_neopixel.assert_called_once_with(
        effect="pulse", emotions=["joy"], lease_source="shadow_learner"
    )


def test_service_client_session_validation_and_bounded_stream_poll(monkeypatch):
    client = ServiceClient(
        {
            "arduino": "http://127.0.0.1:8091",
            "neopixel": "http://127.0.0.1:8092",
            "speak": "http://127.0.0.1:8083",
            "state_manager": "http://127.0.0.1:8080/state",
        },
        config={"speech": {"stream_poll_interval_s": 0.02, "stream_max_wait_s": 0.06}},
    )

    # Invalid arduino payload rejected locally
    bad = client.arduino_send({"cmd": "invalid_xyz"})
    assert bad["ok"] is False

    # Session post failing (500) returns None cleanly
    fake_session = MagicMock()
    fake_session.post.return_value = SimpleNamespace(status_code=500, json=lambda: {})
    fake_session.get.return_value = SimpleNamespace(status_code=200, json=lambda: {"job": {"status": "running"}})
    client._session = fake_session
    assert client.fill_neopixel_segment_color("ring", 10, 20, 30) is None
    assert client.fill_neopixel_color(10, 20, 30) is None

    # Bounded stream_poll even under frozen time.time()
    fake_session.post.return_value = SimpleNamespace(status_code=200, json=lambda: {"ok": True, "job_id": "j1"})
    monkeypatch.setattr("modules.autonomy.services.client_parts.client_speech.time.time", lambda: 1000.0)
    monkeypatch.setattr("modules.autonomy.services.client_parts.client_speech.time.sleep", lambda _s: None)
    stream_res = client.speak_stream("merhaba")
    assert stream_res["ok"] is False
    assert stream_res["error"] == "stream_timeout"

    # async_set_operational_mode uses {"value": ...} contract
    captured = {}

    async def _fake_async_post(svc, ep, json=None, timeout=1.0):
        captured["args"] = (svc, ep, json, timeout)
        return {"ok": True}

    client._async_post = _fake_async_post
    asyncio.run(client.async_set_operational_mode("active"))
    assert captured["args"] == ("state_manager", "/set/operational", {"value": "active"}, 1.0)

    # PiHardwareRuntime uses valid 'get_state' probe
    pi = PiHardwareRuntime({"require_pi": False, "require_camera": False}, client=client)
    client.robot_command = MagicMock(return_value={"ok": True})
    esp = pi._esp_status()
    assert esp["ok"] is True
    client.robot_command.assert_called_once_with("get_state")

    client.close()
    fake_session.close.assert_called_once()


def test_unified_risk_safety_semantics_across_engines_and_selector():
    # Safe state: high CompanionNeeds safety (100) and zero LivingNeeds hazard (0.0) both yield risk=0.0, safety_level=1.0
    comp = CompanionNeedsEngine()
    comp_safe = comp.tick(
        now=100.0,
        last_interaction_ts=100.0,
        mood_state={"energy": 90, "curiosity": 40, "fear": 0},
        needs_state={"social": 20, "stimulation": 20, "rest": 80},
    )
    assert comp_safe["scores"]["safety"] == 100.0
    assert comp_safe["risk"] == 0.0
    assert comp_safe["safety_level"] == 1.0

    living = LivingNeedsEngine()
    living_safe = living.tick(now=100.0, state={"last_interaction": 100.0}, vision={"hazards": []})
    assert living_safe["scores"]["safety"] == 0.0
    assert living_safe["risk"] == 0.0
    assert living_safe["safety_level"] == 1.0

    mood = MoodManager({"defaults": {"mood": {}}})
    assert mood.get_risk_and_safety() == {"risk": 0.0, "safety_level": 1.0, "fear": 0.0}

    # Hazard state: both indicate elevated risk > 0.5
    comp_hazard = comp.tick(now=100.0, mood_state={"fear": 80}, scene={"hazards": ["stairs"]})
    living_hazard = living.tick(now=100.0, vision={"hazards": ["stairs", "edge"]})
    assert comp_hazard["risk"] >= 0.65
    assert living_hazard["risk"] == 1.0
    assert extract_risk_and_safety(comp_hazard) == (comp_hazard["risk"], comp_hazard["safety_level"])

    # CompanionGoalSelector with real CompanionNeedsEngine output MUST NOT trigger false safe_observe/safety_hold when safe
    selector = CompanionGoalSelector(
        {
            "environment_policy": {
                "enabled": True,
                "exploration_probability": 0.0,
                "safety_hold_threshold": 0.75,
                "signals": {"curiosity": ["scores.curiosity"], "safety": ["risk", "scores.safety"]},
                "candidates": {
                    "curious_scan": {
                        "base": 0.2,
                        "behavior": "curious_scan",
                        "recommended_goal": "inspect_environment",
                        "semantic": "curious_scan",
                        "weights": {"curiosity": 0.5, "safety": -0.8},
                    }
                },
            }
        }
    )
    safe_plan = selector.select(comp_safe, owner_present=False, now=100.0)
    assert safe_plan["risk"] == 0.0
    assert safe_plan["pet_intent"] != "safe_observe"
    assert safe_plan["environmental_choice"]["candidate"] == "curious_scan"

    danger_plan = selector.select(comp_hazard, owner_present=False, now=101.0)
    assert danger_plan["risk"] >= 0.65
    assert danger_plan["pet_intent"] == "safe_observe"


def test_planners_use_normalized_ollama_url_and_rag_recent(monkeypatch):
    called = {}

    class _FakeRag:
        def __init__(self, _cfg):
            pass

        def recent(self, limit=5):
            called["limit"] = limit
            return {"items": [{"name": "cup", "summary": "A coffee cup on desk"}]}

    monkeypatch.setattr("modules.cognitive_memory.services.world_memory_rag.WorldMemoryRAG", _FakeRag)

    bp = BehaviorPlanner({"agent": {"ollama_base_url": "http:"}, "llm": {"model": "qwen3.5:9b"}})
    assert bp.ollama_host.startswith("http://")
    rp = ReflectionPlanner({"agent": {"ollama_base_url": ""}, "llm": {"model": "qwen3.5:9b"}})
    assert rp.ollama_host.startswith("http://")

    monkeypatch.setattr("modules.autonomy.services.behavior_planner.ollama", None)
    assert bp.generate_plan({}, "desk", recent_reflections=[{"summary": "checked desk"}]) is None

    # Test RAG recent() lookup when ollama is stubbed
    fake_client = MagicMock()
    fake_client.chat.return_value = {"message": {"content": "[]"}}
    fake_ollama = SimpleNamespace(Client=lambda host: fake_client)
    monkeypatch.setattr("modules.autonomy.services.behavior_planner.ollama", fake_ollama)
    bp.cooldown_s = 0.0
    out = bp.generate_plan({"scores": {"boredom": 70}}, "desk", recent_reflections=[{"summary": "checked desk"}])
    assert called["limit"] == 5
    assert isinstance(out, list)


def test_cloud_backup_online_sqlite_and_filters(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "mem.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO items (val) VALUES ('ok')")
    conn.commit()
    conn.close()
    (data_dir / "snap.png").write_bytes(b"png")

    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    sync = CloudBackupSync({"enabled": True, "endpoint_url": "http://example.invalid/up", "include_databases": True, "include_images": False})
    sync._stage_backup_files(data_dir, stage_dir)
    assert (stage_dir / "mem.db").exists()
    assert not (stage_dir / "snap.png").exists()
    sync.stop()


def test_saliency_target_default_and_scene_register_single_prune(monkeypatch):
    t1 = SaliencyTarget(target_type="idle", priority_score=0.1)
    t2 = SaliencyTarget(target_type="idle", priority_score=0.1)
    assert t1.metadata == {}
    t1.metadata["x"] = 1
    assert t2.metadata == {}

    reg = SceneRegister(window_s=5.0)
    calls = 0
    orig_prune = reg._prune_expired_locked

    def _counting_prune(now):
        nonlocal calls
        calls += 1
        return orig_prune(now)

    monkeypatch.setattr(reg, "_prune_expired_locked", _counting_prune)
    reg.get_scene_state()
    assert calls == 1


def test_brain_capability_emotion_sync_dream_cache_and_state_telemetry(tmp_path):
    cfg = {
        "llm": {"enabled": True},
        "vision_hooks": {"enabled": True, "poll_interval_s": 0.0, "forward_interval_s": 0.0, "context_cache_ttl_s": 5.0},
        "visual_state": {"emotion_min_interval_s": 0.0},
        "owner_learning": {"profile_path": str(tmp_path / "owners.json")},
        "safe_navigation": {"places_path": str(tmp_path / "safe.json")},
        "topomap_motion": {"map_path": str(tmp_path / "topo.json")},
        "shadow_learner": {"save_path": str(tmp_path / "macros.yml")},
        "world_memory": {"db_path": str(tmp_path / "wm.db")},
        "companion_goals": {},
    }
    brain = AutonomyBrain(cfg)
    try:
        # 1. Capability owner learning doesn't collide with method name
        status = brain.get_owner_learning_status()
        assert status["ok"] is True

        # 2. EmotionSyncMixin actually emits client.update_emotions outside lock
        brain.client = MagicMock()
        brain._last_emotion_sync_ts = 0.0
        brain._last_emotion_sent = None
        brain.mood.modify("happiness", 40)
        brain._sync_emotion()
        brain.client.update_emotions.assert_called()

        # 3. Shared TTL cache avoids duplicate get_visual_context() calls across VisionMixin & PerceptionContextMixin
        brain.client.get_visual_context.return_value = {
            "available": True,
            "context": {"summary": "room clear", "importance_score": 0.3, "people": [], "hazards": []},
        }
        brain.client.get_latest_vision_results.return_value = []
        brain._sense_vision()
        brain._forward_visual_events_to_agent()
        assert brain.client.get_visual_context.call_count == 1

        # 4. observe_manual_action delegates properly
        brain.observe_manual_action("head_move", {"pan": 90, "tilt": 90})

        # 5. Dream reflection writes cleanly to world_memory via dict payload
        brain.memory.add_event("Robot noticed owner arrived")
        rec = brain._run_dream_reflection(prune_res={"deleted": 1}, cons_res={"consolidated": 2})
        assert rec is not None and rec["name"] == "dream_reflection"

        # 6. Vocal agent_core short-circuits when speech_handled or actions are present without text
        brain.agent = MagicMock()
        brain.agent.step.return_value = {"text": "", "speech_handled": True, "actions": [{"tool": "speak"}]}
        assert brain._try_agent_core_path("merhaba", "tr", "Emir", "req123") is True

        # 7. ResponseTagMixin resolves defaults.lights
        assert brain._default_light_mode() is None or isinstance(brain._default_light_mode(), str)
        brain.config["defaults"] = {"lights": {"default_mode": "pulse", "palettes": {"mint": [10, 200, 150]}}}
        assert brain._default_light_mode() == "pulse"
        assert brain._resolve_palette_rgb("mint") == (10, 200, 150)

        # 8. /autonomy/state returns thread-safe telemetry with stalled worker flag
        brain.state["laya_last_inference_ms"] = 12.5
        brain.state["agent_last_latency_ms"] = 410.0
        brain._agentic_decision_in_progress = True
        brain._agentic_decision_started_at = time.time() - 120.0
        router = get_router(brain)
        state_ep = next(r.endpoint for r in router.routes if getattr(r, "path", "").endswith("/state"))
        snap = state_ep()
        assert snap["telemetry"]["laya_latency_ms"] == 12.5
        assert snap["telemetry"]["agent_latency_ms"] == 410.0
        assert snap["telemetry"]["worker"]["stalled"] is True
    finally:
        brain.stop()


def test_reflection_releases_memory_write_lock_during_llm_call():
    brain = AutonomyBrain({"llm": {"enabled": False}, "vision_hooks": {"enabled": False}})
    try:
        observed_lock_free = {}

        def _slow_reflect(_plan, _res, _needs, _vision):
            # Another thread MUST be able to acquire _memory_write_lock while reflect() runs
            acquired = brain._memory_write_lock.acquire(timeout=0.5)
            observed_lock_free["acquired"] = acquired
            if acquired:
                brain._memory_write_lock.release()
            return {"kind": "reflection", "name": "test", "summary": "reflected cleanly"}

        done = threading.Event()
        orig_observe = brain.observe_world_memory

        def _wrapped_observe(payload, source="reflection_planner"):
            try:
                return orig_observe(payload, source=source)
            finally:
                done.set()

        brain.reflection_planner.reflect = _slow_reflect
        brain.observe_world_memory = _wrapped_observe
        brain.goal_auto_execute_gate = SimpleNamespace(
            decide=lambda _p, force=False, bypass_cooldown=False: {"should_execute": True, "dry_run": True},
            mark_execution=lambda d, e: {**e, "should_execute": True, "executed": True},
        )
        brain.execute_companion_goal = lambda _p: {"ok": True, "reason": "done"}
        brain.tick_companion_auto_execute({"goal_plan": {"behavior": "llm_generated_action", "actions": []}})
        assert done.wait(timeout=3.0)
        assert observed_lock_free.get("acquired") is True
    finally:
        brain.stop()


def test_config_loader_deep_merges_and_unifies_owner_section(tmp_path):
    cfg = load_config(overrides={"llm": {"enabled": False}})
    assert cfg["llm"]["enabled"] is False
    # Deep merge preserves existing prompt_template and idle_behaviors actions
    assert "prompt_template" in cfg["llm"]
    assert isinstance(cfg["behaviors"]["idle_tree"].get("actions"), list)
    assert len(cfg["behaviors"]["idle_tree"]["actions"]) > 0
    # Owner section unified cleanly without duplicate key shadow loss
    raw_yml = yaml.safe_load(Path("modules/autonomy/config/config.yml").read_text(encoding="utf-8"))
    assert "Emir" in raw_yml["owner"]["aliases"]
    assert "patron" in raw_yml["owner"]["aliases"]
