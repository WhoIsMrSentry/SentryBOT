from __future__ import annotations

import json
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.vlm_bridge.api.config_routes import get_config_router
from modules.vlm_bridge.api.person import get_person_router
from modules.vlm_bridge.config_loader import load_config
from modules.vlm_bridge.services.face_manager import FaceManager
from modules.vlm_bridge.services.head_control_arbiter import HeadCommand, HeadControlArbiter
from modules.vlm_bridge.services.person_identity import PersonIdentityManager
from modules.vlm_bridge.services.processor_follow import ProcessorFollowMixin
from modules.vlm_bridge.services.processor_identity import ProcessorIdentityMixin
from modules.vlm_bridge.services.processor_stream import ProcessorStreamMixin
from modules.vlm_bridge.services.vision_request_gate import VisionRequestGate


def test_vlm_results_auth_fail_closed_and_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    ingested: list = []

    proc = SimpleNamespace(
        config={"remote": {"accept_results": True, "auth_token": ""}},
        ingest_remote_results=lambda objs: ingested.append(objs) or {"accepted": len(objs)},
    )
    app = FastAPI()
    app.include_router(get_config_router(proc, "http://127.0.0.1:8080"), prefix="/vlm")
    client = TestClient(app)

    monkeypatch.delenv("SENTRYBOT_VLM_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MM_AUTH_TOKEN", raising=False)

    # Empty or placeholder token must fail closed (401)
    assert client.post("/vlm/results", json={"objects": [{"label": "cup"}]}).status_code == 401
    proc.config["remote"]["auth_token"] = "changeme"
    assert (
        client.post(
            "/vlm/results",
            headers={"X-Auth-Token": "changeme"},
            json={"objects": [{"label": "cup"}]},
        ).status_code
        == 401
    )

    # Env token acts as secure fallback
    monkeypatch.setenv("SENTRYBOT_VLM_AUTH_TOKEN", "prod-vlm-secret")
    assert (
        client.post(
            "/vlm/results",
            headers={"X-Auth-Token": "wrong"},
            json={"objects": [{"label": "cup"}]},
        ).status_code
        == 401
    )

    # Schema validation rejects non-list objects
    assert (
        client.post(
            "/vlm/results",
            headers={"X-Auth-Token": "prod-vlm-secret"},
            json={"objects": "invalid"},
        ).status_code
        == 422
    )

    ok_resp = client.post(
        "/vlm/results",
        headers={"X-Auth-Token": "prod-vlm-secret"},
        json={"objects": [{"label": "cup", "conf": 0.9, "bbox": [1, 2, 30, 40], "distance": 1.25}]},
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["ok"] is True
    assert len(ingested) == 1
    assert ingested[0][0]["label"] == "cup"
    assert ingested[0][0]["confidence"] == 0.9
    assert ingested[0][0]["distance_m"] == 1.25


def test_head_arbiter_callback_runs_unlocked_and_settles_target() -> None:
    arb = HeadControlArbiter(
        {
            "max_rate_hz": 1000.0,
            "deadband_deg": 2.0,
            "smooth_alpha": 0.5,
            "active_lock_ttl_s": 2.0,
        }
    )
    lock_free_during_cb: list[bool] = []
    sent_poses: list[tuple[float, float]] = []

    def _move_cb(pan: float, tilt: float) -> None:
        acquired = arb._lock.acquire(blocking=False)
        lock_free_during_cb.append(acquired)
        if acquired:
            arb._lock.release()
        sent_poses.append((pan, tilt))

    arb.set_move_callback(_move_cb)

    # Repeating the exact same target should converge within <0.5 deg without deadband freeze
    for _ in range(12):
        arb.request_move(HeadCommand(pan=110.0, tilt=90.0, source="owner_follow", priority=85))
        time.sleep(0.002)

    assert all(lock_free_during_cb)
    assert sent_poses[-1] == (110.0, 90.0)

    # Active owner_follow move automatically guards against lower-priority idle/autonomy drift
    low = arb.request_move(HeadCommand(pan=70.0, tilt=90.0, source="autonomy", priority=30))
    assert low["ok"] is False
    assert low["reason"] == "source_locked"
    assert low["locked_by"] == "owner_follow"


def test_processor_follow_pd_and_target_lost_sweep() -> None:
    class _FollowHarness(ProcessorFollowMixin):
        def __init__(self) -> None:
            self._follow_cfg = {
                "track_interval_s": 0.0,
                "pd_kp": 0.85,
                "pd_kd": 0.12,
                "pan_gain_deg": 50.0,
                "tilt_gain_deg": 32.0,
                "center_pan": 90,
                "center_tilt": 90,
                "min_pan": 35,
                "max_pan": 145,
                "min_tilt": 65,
                "max_tilt": 125,
                "sweep_enabled": True,
                "sweep_after_lost_frames": 2,
                "sweep_max_steps": 4,
                "sweep_step_deg": 5.0,
                "sweep_span_deg": 15.0,
                "active_lock_ttl_s": 1.0,
            }
            self.head_arbiter = HeadControlArbiter({"max_rate_hz": 1000.0, "deadband_deg": 0.5})
            self.moves: list[tuple[float, float]] = []
            self.head_arbiter.set_move_callback(lambda p, t: self.moves.append((p, t)))
            self._follow_active = True
            self._follow_target = "owner"
            self._follow_tracker = None
            self._follow_current_bbox = None
            self._follow_last_track_ts = 0.0
            self._follow_lost_frames = 0
            self._sweep_step = 0
            self._last_target_dir_x = 1

    h = _FollowHarness()
    # Owner bbox on right side -> positive pan > 90
    h._drive_follow([{"name": "owner", "bbox": [460, 200, 560, 320]}], (480, 640, 3))
    assert len(h.moves) == 1
    assert h.moves[0][0] > 90.0
    assert h._last_target_dir_x == 1

    # First lost frame waits for threshold; second lost frame triggers bounded sweep
    h._follow_last_track_ts = time.monotonic() - 1.0
    assert h._sweep_on_target_lost() is None
    assert h._follow_lost_frames == 1

    h._follow_last_track_ts = time.monotonic() - 1.0
    h.head_arbiter._last_cmd_time = 0.0
    res = h._sweep_on_target_lost()
    assert res is not None and res.get("ok") is True
    assert h._sweep_step == 1

    # Re-acquiring target resets sweep counters
    h._follow_last_track_ts = time.monotonic() - 1.0
    h._drive_follow([{"name": "owner", "bbox": [300, 200, 340, 280]}], (480, 640, 3))
    assert h._sweep_step == 0
    assert h._follow_lost_frames == 0


def test_face_manager_skips_second_yunet_scan_when_raw_face_passed(tmp_path) -> None:
    fm = FaceManager(data_dir=str(tmp_path), social_db=False)
    detect_mock = MagicMock(side_effect=AssertionError("second YuNet scan must not run"))
    fm._yunet = SimpleNamespace(is_available=True, detect=detect_mock)
    vec = np.ones((1, 128), dtype=np.float32)
    fm._sface = SimpleNamespace(
        is_available=True,
        COSINE_MATCH_THRESHOLD=0.363,
        extract_feature=lambda img, raw: vec,
        match=lambda a, b: 0.9,
    )
    fm._known_embeddings["Alice"] = vec

    full = np.zeros((120, 120, 3), dtype=np.uint8)
    crop = np.zeros((40, 40, 3), dtype=np.uint8)
    raw_face = np.zeros((1, 15), dtype=np.float32)

    name, score = fm.identify_face_with_score(crop, full_frame=full, raw_face=raw_face, is_cropped=True)
    assert name == "Alice"
    assert score > 0.8
    assert detect_mock.call_count == 0


def test_person_identity_locked_api_single_upsert_and_atomic_json(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Verify single-record SQLite/SocialDB upsert rather than full table rewrite
    upserts: list[str] = []

    class _DummyPersonsRepo:
        def list_all(self) -> list:
            return []

        def upsert(self, **kwargs) -> None:
            upserts.append(kwargs["person_id"])

    dummy_social = SimpleNamespace(persons=_DummyPersonsRepo())
    pim_db = PersonIdentityManager(store_path=str(tmp_path / "unused.json"), social_db=dummy_social)
    p1 = pim_db.remember_person("Alice", relationship="friend", recognition_level=3)
    p2 = pim_db.remember_person("Bob", relationship="known", recognition_level=2)
    upserts.clear()

    # Router /person/relationship must use locked public helper & update only matching person
    proc = SimpleNamespace(person_identity=pim_db)
    app = FastAPI()
    app.include_router(get_person_router(proc, "http://127.0.0.1:8080"), prefix="/vlm")
    client = TestClient(app)

    resp = client.post(
        "/vlm/person/relationship",
        json={"name": "Alice", "relationship": "family", "recognition_level": 4},
    )
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert upserts == [p1.person_id]
    assert p2.person_id not in upserts

    people_resp = client.get("/vlm/people")
    assert people_resp.status_code == 200
    assert len(people_resp.json()["people"]) == 2

    # 2. Verify JSON fallback writes atomically without stray .tmp files
    monkeypatch.setitem(sys.modules, "modules.cognitive_memory", None)
    monkeypatch.setitem(sys.modules, "modules.cognitive_memory.services.repositories", None)
    json_path = tmp_path / "people.json"
    pim_json = PersonIdentityManager(store_path=str(json_path), social_db=None)
    pim_json._social_db = None
    import os

    pim_json.remember_person("Charlie", relationship="friend", recognition_level=3)
    assert json_path.exists()
    assert not (tmp_path / f"people.json.tmp.{os.getpid()}").exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(loaded) == 1
    assert next(iter(loaded.values()))["name"] == "Charlie"


def test_vision_request_gate_disabled_locked_and_config_single_model_mode(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = VisionRequestGate({"enabled": False})
    ids: list[str] = []
    lock = threading.Lock()

    def _worker() -> None:
        dec = gate.decide(reason="idle_refresh")
        with lock:
            ids.append(dec.request_id)

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(ids) == 10
    assert len(set(ids)) == 10

    monkeypatch.setenv("VLM_OLLAMA_BASE_URL", "http:")
    with pytest.raises(ValueError):
        load_config(overrides={"llm": {"single_model_mode": True, "model": "llava:7b"}})

    cfg = load_config(
        overrides={"llm": {"single_model_mode": False, "model": "llava:7b"}, "ollama": {"base_url": "http:"}}
    )
    assert cfg["llm"]["model"] == "llava:7b"
    assert cfg["ollama"]["base_url"].startswith("http://")
    assert "/api/generate" not in cfg["ollama"]["base_url"]


def test_onsensor_object_results_coord_space_and_generate_frames_stops() -> None:
    class _IdentityHarness(ProcessorIdentityMixin):
        def _latest_onsensor_snapshot(self):
            return SimpleNamespace(
                width=640,
                height=480,
                detections=[SimpleNamespace(label="cup", score=0.88, bbox_xyxy_norm=[0.25, 0.5, 0.75, 1.0])],
            )

    out = _IdentityHarness()._onsensor_object_results((480, 640, 3))
    assert len(out) == 1
    assert out[0]["coord_space"] == "px"
    assert out[0]["bbox"] == [160, 240, 480, 480]
    assert out[0]["bbox_xyxy_norm"] == [0.25, 0.5, 0.75, 1.0]

    class _StreamHarness(ProcessorStreamMixin):
        def __init__(self) -> None:
            self._stop_event = threading.Event()
            self._frame_lock = threading.Lock()
            self._latest_annotated_frame = b"fake-jpeg"
            self._mjpeg_cond = threading.Condition()
            self._mjpeg_subscribers = 0
            self._mjpeg_seq = 1

    sh = _StreamHarness()
    gen = sh.generate_frames()
    chunk = next(gen)
    assert b"fake-jpeg" in chunk
    assert sh._mjpeg_subscribers == 1

    sh._stop_event.set()
    with sh._mjpeg_cond:
        sh._mjpeg_cond.notify_all()
    assert list(gen) == []
    assert sh._mjpeg_subscribers == 0
