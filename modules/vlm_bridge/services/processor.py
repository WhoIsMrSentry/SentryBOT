from __future__ import annotations

import logging
import os
import threading
import time
import base64
from datetime import datetime
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

import cv2
import requests

try:
    from .face_manager import FaceManager
except Exception:
    try:
        from modules.vlm_bridge.services.face_manager import FaceManager
    except Exception:
        FaceManager = None  # type: ignore

try:
    from .cascade_loader import load_frontal_face_cascade
except Exception:
    from modules.vlm_bridge.services.cascade_loader import load_frontal_face_cascade  # type: ignore

try:
    from .semantic_describer import SemanticDescriber
except Exception:
    from modules.vlm_bridge.services.semantic_describer import SemanticDescriber  # type: ignore

try:
    from .people_memory import PeopleMemory
except Exception:
    from modules.vlm_bridge.services.people_memory import PeopleMemory  # type: ignore

try:
    from .action_dispatcher import VisionActionDispatcher
except Exception:
    from modules.vlm_bridge.services.action_dispatcher import VisionActionDispatcher  # type: ignore

try:
    from .llm_client import generate_text
except Exception:
    from modules.vlm_bridge.services.llm_client import generate_text  # type: ignore

try:
    from .person_identity import PersonIdentityManager
except Exception:
    try:
        from modules.vlm_bridge.services.person_identity import PersonIdentityManager
    except Exception:
        PersonIdentityManager = None  # type: ignore

try:
    from .visual_context import VisionFrameContext, VisualContextCache
except Exception:
    try:
        from modules.vlm_bridge.services.visual_context import VisionFrameContext, VisualContextCache
    except Exception:
        VisionFrameContext = None  # type: ignore
        VisualContextCache = None  # type: ignore

try:
    from .ollama_vlm_client import OllamaVLMClient
except Exception:
    try:
        from modules.vlm_bridge.services.ollama_vlm_client import OllamaVLMClient
    except Exception:
        OllamaVLMClient = None  # type: ignore

try:
    from .vision_sampler import VisionSampler
except Exception:
    VisionSampler = None  # type: ignore

try:
    from .vision_event_bus import (
        VisionEventBus,
        EVENT_HAZARD_DETECTED,
        EVENT_NEW_PERSON,
        EVENT_OWNER_SEEN,
        EVENT_SCENE_CHANGED,
        EVENT_VLM_RESULT_READY,
    )
except Exception:
    VisionEventBus = None  # type: ignore
    EVENT_HAZARD_DETECTED = "hazard_detected"
    EVENT_NEW_PERSON = "new_person"
    EVENT_OWNER_SEEN = "owner_seen"
    EVENT_SCENE_CHANGED = "scene_changed"
    EVENT_VLM_RESULT_READY = "vlm_result_ready"

try:
    from .head_control_arbiter import HeadControlArbiter, HeadCommand
except Exception:
    HeadControlArbiter = None  # type: ignore
    HeadCommand = None  # type: ignore

try:
    from modules.camera.services.onsensor_bus import OnSensorEventBus, OnSensorSnapshot  # type: ignore
except Exception:
    OnSensorEventBus = None  # type: ignore
    OnSensorSnapshot = None  # type: ignore


logger = logging.getLogger("vlm_bridge")


def _create_csrt_tracker() -> Optional[Any]:
    if hasattr(cv2, "TrackerCSRT_create"):
        try:
            return cv2.TrackerCSRT_create()
        except Exception:
            pass
    legacy = getattr(cv2, "legacy", None)
    if legacy is not None and hasattr(legacy, "TrackerCSRT_create"):
        try:
            return legacy.TrackerCSRT_create()
        except Exception:
            pass
    return None


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class VisionProcessor:
    """YOLO'suz VLM Bridge isleyici.

    Yerelde:
    - OpenCV Haar face detect
    - OpenCV ORB+FLANN ile kimliklendirme
    - CSRT ile takip

    Uzakta:
    - /vlm/results ile gelen sonuclari cache'ler.
    """

    def __init__(self, config: Dict[str, Any]):
        try:
            from modules.gateway.url import resolve_gateway_base_url, rewrite_loopback_urls

            self._gateway_base = resolve_gateway_base_url(config)
            config = rewrite_loopback_urls(config, self._gateway_base)
        except Exception:
            self._gateway_base = "http://127.0.0.1:8080"
        self.config = config
        vision_cfg = config.get("vision", {}) if isinstance(config, dict) else {}

        self.processing_mode = str(vision_cfg.get("processing_mode", "local")).strip().lower()
        self.camera_source = vision_cfg.get("camera_source", 0)
        self._max_camera_wait_attempts = max(1, int(vision_cfg.get("max_camera_wait_attempts", 5)))
        self._camera_gave_up = False
        self._context_max_age_s = max(5.0, float(vision_cfg.get("context_max_age_s", 45.0)))
        self.conf_threshold = float(vision_cfg.get("confidence_threshold", 0.5))

        raw_modes = vision_cfg.get("modes", {}) if isinstance(vision_cfg.get("modes", {}), dict) else {}
        self.mode_flags: Dict[str, bool] = {
            "objects": bool(raw_modes.get("objects", True)),
            "people": bool(raw_modes.get("people", True)),
            "faces": bool(raw_modes.get("faces", True)),
            "depth": bool(raw_modes.get("depth", False)),
            "ocr": bool(raw_modes.get("ocr", False)),
            "hazards": bool(raw_modes.get("hazards", True)),
            "semantic_scene": bool(raw_modes.get("semantic_scene", True)),
        }
        raw_categories = vision_cfg.get("mode_categories", {}) if isinstance(vision_cfg.get("mode_categories", {}), dict) else {}
        def _bool_map(section: Dict[str, Any]) -> Dict[str, bool]:
            return {str(k): bool(v) for k, v in (section or {}).items()}
        self.mode_categories: Dict[str, Dict[str, bool]] = {
            "local": _bool_map(raw_categories.get("local", {"face_match": True, "visual_logger": True})),
            "remote": _bool_map(raw_categories.get("remote", {
                "objects": self.mode_flags["objects"],
                "people": self.mode_flags["people"],
                "faces": self.mode_flags["faces"],
                "ocr": self.mode_flags["ocr"],
                "hazards": self.mode_flags["hazards"],
                "semantic_scene": self.mode_flags["semantic_scene"],
                "depth": self.mode_flags["depth"],
            })),
            "onsensor": _bool_map(raw_categories.get("onsensor", {"tiny_detect": False, "tiny_pose": False})),
        }
        # Optional ergonomics buckets (backward compatible aliases for mode_categories)
        lm = vision_cfg.get("local_modes")
        rm = vision_cfg.get("remote_modes")
        om = vision_cfg.get("onsensor_modes") or vision_cfg.get("sensor_modes")
        if isinstance(lm, dict):
            for key, value in lm.items():
                if key in self.mode_categories["local"]:
                    self.mode_categories["local"][key] = bool(value)
        if isinstance(rm, dict):
            for key, value in rm.items():
                if key in self.mode_categories["remote"]:
                    self.mode_categories["remote"][key] = bool(value)
        if isinstance(om, dict):
            for key, value in om.items():
                if key in self.mode_categories["onsensor"]:
                    self.mode_categories["onsensor"][key] = bool(value)
        disabled = vision_cfg.get("disabled_modes") or {}
        if isinstance(disabled, dict):
            for key, value in disabled.items():
                if not bool(value):
                    continue
                for cat_name, bucket in list(self.mode_categories.items()):
                    if key in bucket:
                        bucket[key] = False
                if key in self.mode_flags:
                    self.mode_flags[key] = False
        self.mode_profiles: Dict[str, Dict[str, bool]] = {
            "balanced": dict(self.mode_flags),
            "people_focus": {
                "objects": False,
                "people": True,
                "faces": True,
                "depth": False,
                "ocr": False,
                "hazards": True,
                "semantic_scene": True,
            },
            "objects_focus": {
                "objects": True,
                "people": False,
                "faces": False,
                "depth": False,
                "ocr": False,
                "hazards": True,
                "semantic_scene": True,
            },
            "assistive": {
                "objects": True,
                "people": True,
                "faces": True,
                "depth": bool(raw_modes.get("depth", False)),
                "ocr": bool(raw_modes.get("ocr", False)),
                "hazards": True,
                "semantic_scene": True,
            },
            "minimal": {
                "objects": False,
                "people": False,
                "faces": False,
                "depth": False,
                "ocr": False,
                "hazards": False,
                "semantic_scene": False,
            },
        }

        self._face_cascade = load_frontal_face_cascade(logger)

        self.face_manager = None
        if self.processing_mode == "local" and FaceManager is not None:
            try:
                face_match_cfg = vision_cfg.get("face_match", {}) if isinstance(vision_cfg.get("face_match", {}), dict) else {}
                self.face_manager = FaceManager(
                    ratio_test=float(face_match_cfg.get("ratio_test", 0.72)),
                    min_good_matches=int(face_match_cfg.get("min_good_matches", 10)),
                    min_score=float(face_match_cfg.get("min_score", 0.15)),
                )
            except Exception as exc:
                logger.warning("FaceManager init failed: %s", exc)

        self._stop_event = threading.Event()
        self._capture_thread: Optional[threading.Thread] = None
        self._inference_thread: Optional[threading.Thread] = None

        self._frame_lock = threading.Lock()
        self._latest_raw_frame: Optional[Any] = None
        self._latest_annotated_frame: Optional[bytes] = None

        self.latest_results: List[Dict[str, Any]] = []
        self.blind_mode_enabled = bool(vision_cfg.get("blind_mode", {}).get("enabled", False))
        self.last_blind_announcement = 0.0
        self.last_alert_announcement = 0.0
        self._last_person_greet: Dict[str, float] = {}

        # Follow mode state (face lock + CSRT)
        follow_cfg = vision_cfg.get("follow", {}) if isinstance(vision_cfg.get("follow", {}), dict) else {}
        self._follow_cfg = {
            "enabled": bool(follow_cfg.get("enabled", True)),
            "track_interval_s": float(follow_cfg.get("track_interval_s", 0.12)),
            "pan_gain_deg": float(follow_cfg.get("pan_gain_deg", 50.0)),
            "tilt_gain_deg": float(follow_cfg.get("tilt_gain_deg", 32.0)),
            "center_pan": int(follow_cfg.get("center_pan", 90)),
            "center_tilt": int(follow_cfg.get("center_tilt", 90)),
            "min_pan": int(follow_cfg.get("min_pan", 35)),
            "max_pan": int(follow_cfg.get("max_pan", 145)),
            "min_tilt": int(follow_cfg.get("min_tilt", 65)),
            "max_tilt": int(follow_cfg.get("max_tilt", 125)),
            "max_lost_frames": int(follow_cfg.get("max_lost_frames", 18)),
        }
        self._follow_active = False
        self._follow_target: Optional[str] = None
        self._follow_tracker: Optional[Any] = None
        self._follow_lost_frames = 0
        self._follow_last_track_ts = 0.0
        self._follow_current_bbox: Optional[Tuple[int, int, int, int]] = None
        self._track_callback: Optional[Callable[..., Any]] = None

        self.semantic = SemanticDescriber(config)
        self.memory = PeopleMemory()

        # Living Vision Agent components
        if PersonIdentityManager is not None:
            person_data_path = vision_cfg.get("person_identity_store", "")
            self.person_identity = PersonIdentityManager(
                store_path=person_data_path,
                face_manager=self.face_manager,
                people_memory=self.memory,
            )
        else:
            self.person_identity = None
            logger.warning("PersonIdentityManager not available")

        if VisualContextCache is not None:
            vctx_cfg = config.get("visual_context", {}) if isinstance(config.get("visual_context", {}), dict) else {}
            max_hist = max(1, int(vctx_cfg.get("cache_history_size", 5)))
            self.visual_context_cache = VisualContextCache(max_history=max_hist)
        else:
            self.visual_context_cache = None
            logger.warning("VisualContextCache not available")

        # Remote VLM client (Ollama or Google AI Studio)
        vlm_cfg = config.get("vision_llm", {}) if isinstance(config.get("vision_llm", {}), dict) else {}
        if vlm_cfg.get("enabled", True):
            try:
                try:
                    from .google_vlm_client import create_vision_llm_client
                except Exception:
                    from modules.vlm_bridge.services.google_vlm_client import create_vision_llm_client  # type: ignore

                self.vlm_client = create_vision_llm_client(config)
                provider = str(vlm_cfg.get("provider", "ollama"))
                logger.info(
                    "[vlm_bridge] Vision LLM client initialized (%s): %s",
                    provider,
                    getattr(self.vlm_client, "model", "unknown"),
                )
            except Exception as exc:
                logger.warning("VLM client init failed: %s", exc)
                self.vlm_client = None
        else:
            self.vlm_client = None
            logger.info("[vlm_bridge] Remote VLM client disabled or unavailable")

        mm_cfg = config.get("remote_multimodal", {}) if isinstance(config.get("remote_multimodal", {}), dict) else {}
        self.remote_mm_enabled = bool(mm_cfg.get("enabled", False))
        self.remote_mm_endpoint = str(mm_cfg.get("endpoint", "http://127.0.0.1:8091/vision/analyze")).strip()
        self.remote_mm_timeout_s = float(mm_cfg.get("timeout_s", 6.0))
        self.remote_mm_auth_token = str(mm_cfg.get("auth_token", "")).strip()
        default_ocr_endpoint = self.remote_mm_endpoint.replace("/vision/analyze", "/vision/ocr") if self.remote_mm_endpoint else ""
        self.remote_mm_ocr_endpoint = str(mm_cfg.get("ocr_endpoint", default_ocr_endpoint)).strip()
        self.remote_mm_ocr_timeout_s = float(mm_cfg.get("ocr_timeout_s", 10.0))
        ocr_langs = mm_cfg.get("ocr_languages", ["en", "tr"])
        if isinstance(ocr_langs, (list, tuple)):
            self.remote_mm_ocr_languages = [str(x).strip() for x in ocr_langs if str(x).strip()]
        else:
            self.remote_mm_ocr_languages = ["en", "tr"]

        actions_cfg = config.get("actions", {}) if isinstance(config, dict) else {}
        endpoint = str(actions_cfg.get("endpoint", "http://localhost:8080/autonomy/apply_actions"))
        timeout = float(actions_cfg.get("timeout", 1.5))
        enabled = bool(actions_cfg.get("default_apply", False))
        self.action_dispatcher = VisionActionDispatcher(endpoint=endpoint, timeout=timeout, enabled=enabled)
        self.vision_sampler = VisionSampler(vlm_cfg) if VisionSampler is not None else None
        self.event_bus = VisionEventBus() if VisionEventBus is not None else None
        self.head_arbiter = HeadControlArbiter(self._follow_cfg) if HeadControlArbiter is not None else None
        if self.head_arbiter is not None:
            self.head_arbiter.set_move_callback(lambda pan, tilt: self._send_track(int(pan), int(tilt), 0))

        if self.processing_mode == "local":
            logger.info("[vlm_bridge] Local mode: OpenCV face recognition + CSRT tracking active")
        else:
            logger.info("[vlm_bridge] Remote mode: waiting for /vlm/results payloads")

        self._onsensor_bus: Optional[Any] = None
        self._onsensor_unsub: Optional[Callable[[], None]] = None
        self._onsensor_lock = threading.Lock()
        self._latest_onsensor: Optional[Any] = None

        # Runtime realtime profiles for VLM bridge latency tuning.
        self._realtime_profiles: Dict[str, Dict[str, Any]] = {
            "fast": {
                "vlm_timeout_s": 14.0,
                "vlm_min_interval_s": 4.0,
                "vlm_num_predict": 220,
                "follow_track_interval_s": 0.10,
            },
            "normal": {
                "vlm_timeout_s": 20.0,
                "vlm_min_interval_s": 5.0,
                "vlm_num_predict": 320,
                "follow_track_interval_s": 0.12,
            },
        }
        self._active_realtime_profile = "fast"

    def get_modes(self) -> Dict[str, bool]:
        return dict(self.mode_flags)

    def get_mode_categories(self) -> Dict[str, Dict[str, bool]]:
        """Return the hierarchical (local | remote | onsensor) mode map."""
        return {
            "local": dict(self.mode_categories.get("local", {})),
            "remote": dict(self.mode_categories.get("remote", {})),
            "onsensor": dict(self.mode_categories.get("onsensor", {})),
        }

    def set_mode_categories(self, updates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Patch the hierarchical mode map. ``updates`` is keyed by category."""
        changed: Dict[str, Dict[str, bool]] = {}
        for category, payload in (updates or {}).items():
            if category not in self.mode_categories or not isinstance(payload, dict):
                continue
            for key, value in payload.items():
                if key in self.mode_categories[category]:
                    self.mode_categories[category][key] = bool(value)
                    changed.setdefault(category, {})[key] = self.mode_categories[category][key]
        return {"ok": True, "changed": changed, "mode_categories": self.get_mode_categories()}

    def list_profiles(self) -> List[str]:
        return sorted(self.mode_profiles.keys())

    def set_modes(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        changed: Dict[str, bool] = {}
        for key, value in updates.items():
            if key in self.mode_flags:
                self.mode_flags[key] = bool(value)
                changed[key] = self.mode_flags[key]
        return {"ok": True, "changed": changed, "modes": self.get_modes()}

    def apply_mode_profile(self, name: str) -> Dict[str, Any]:
        profile = self.mode_profiles.get(str(name).strip().lower())
        if not profile:
            return {"ok": False, "error": "unknown_profile", "profiles": self.list_profiles()}
        self.mode_flags.update(profile)
        return {"ok": True, "profile": str(name).strip().lower(), "modes": self.get_modes()}

    def set_processing_mode(self, mode: str) -> Dict[str, Any]:
        m = str(mode or "").strip().lower()
        if m not in {"local", "remote"}:
            return {"ok": False, "error": "invalid_mode", "allowed": ["local", "remote"]}
        if m == self.processing_mode:
            return {"ok": True, "processing_mode": self.processing_mode}

        if m == "remote":
            self.stop_stream_processing()
            self.processing_mode = "remote"
            return {"ok": True, "processing_mode": self.processing_mode}

        # switch remote -> local
        self.processing_mode = "local"
        self.start_stream_processing()
        return {"ok": True, "processing_mode": self.processing_mode}

    def get_realtime_profile_status(self) -> Dict[str, Any]:
        active = self._active_realtime_profile
        return {
            "ok": True,
            "active": active,
            "profiles": sorted(self._realtime_profiles.keys()),
            "settings": dict(self._realtime_profiles.get(active, {})),
        }

    def apply_realtime_profile(self, mode: str) -> Dict[str, Any]:
        key = str(mode or "").strip().lower()
        profile = self._realtime_profiles.get(key)
        if not profile:
            return {
                "ok": False,
                "error": "unknown_profile",
                "profiles": sorted(self._realtime_profiles.keys()),
            }

        self._active_realtime_profile = key
        applied: Dict[str, Any] = {}

        if self.vlm_client is not None:
            if "vlm_timeout_s" in profile:
                self.vlm_client.timeout = float(profile["vlm_timeout_s"])
                applied["vlm_timeout_s"] = self.vlm_client.timeout
            if "vlm_min_interval_s" in profile:
                self.vlm_client.min_interval_s = float(profile["vlm_min_interval_s"])
                applied["vlm_min_interval_s"] = self.vlm_client.min_interval_s
            if "vlm_num_predict" in profile and hasattr(self.vlm_client, "num_predict"):
                self.vlm_client.num_predict = int(profile["vlm_num_predict"])
                applied["vlm_num_predict"] = self.vlm_client.num_predict

        if "follow_track_interval_s" in profile:
            self._follow_cfg["track_interval_s"] = float(profile["follow_track_interval_s"])
            applied["follow_track_interval_s"] = self._follow_cfg["track_interval_s"]

        return {"ok": True, "active": key, "applied": applied}

    # -----------------------------------------------------------------
    # Public control API
    # -----------------------------------------------------------------
    def set_track_callback(self, callback: Callable[..., Any]) -> None:
        self._track_callback = callback

    def start_follow(self, person: Optional[str] = None) -> Dict[str, Any]:
        if not self._follow_cfg.get("enabled", True):
            return {"ok": False, "error": "follow mode disabled"}

        self._follow_active = True
        self._follow_target = str(person).strip() if person else None
        self._follow_tracker = None
        self._follow_lost_frames = 0
        self._follow_current_bbox = None

        if self.processing_mode == "local":
            self.start_stream_processing()

        status = self.follow_status()
        status["ok"] = True
        return status

    def stop_follow(self) -> Dict[str, Any]:
        self._follow_active = False
        self._follow_target = None
        self._follow_tracker = None
        self._follow_lost_frames = 0
        self._follow_current_bbox = None
        return {"ok": True, **self.follow_status()}

    def follow_status(self) -> Dict[str, Any]:
        return {
            "active": bool(self._follow_active),
            "target": self._follow_target,
            "tracking": bool(self._follow_tracker is not None),
            "bbox": list(self._follow_current_bbox) if self._follow_current_bbox else None,
            "mode": self.processing_mode,
        }

    # -----------------------------------------------------------------
    # Streaming lifecycle
    # -----------------------------------------------------------------
    def is_camera_input_available(self) -> bool:
        """True when local vision can read a live camera frame (not gave up / healthz dead)."""
        if str(self.processing_mode).strip().lower() != "local":
            return True
        if self._is_http_camera_source():
            ready = self._http_camera_ready()
            if ready and self._camera_gave_up:
                self._camera_gave_up = False
            return ready and not self._camera_gave_up
        if self._camera_gave_up:
            return False
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                return True
        thread = self._capture_thread
        return thread is not None and thread.is_alive()

    def start_stream_processing(self) -> None:
        if self.processing_mode != "local":
            logger.debug("start_stream_processing() ignored in remote mode")
            return
        self._camera_gave_up = False
        if self._capture_thread and self._capture_thread.is_alive():
            return

        self._stop_event.clear()
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        self._inference_thread = threading.Thread(target=self._inference_loop, daemon=True)
        self._inference_thread.start()

        logger.info("Vision processing started (OpenCV face mode)")

    def stop_stream_processing(self) -> None:
        if self.processing_mode != "local":
            return
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
        if self._inference_thread:
            self._inference_thread.join(timeout=2.0)
        logger.info("Vision processing stopped")

    def _is_http_camera_source(self) -> bool:
        src = self.camera_source
        return isinstance(src, str) and src.lower().startswith(("http://", "https://"))

    def _camera_probe_url(self) -> Optional[str]:
        if not self._is_http_camera_source():
            return None
        src = str(self.camera_source)
        if "/camera/video" in src:
            return src.replace("/camera/video", "/camera/healthz")
        return src

    def _http_camera_ready(self) -> bool:
        probe = self._camera_probe_url()
        if not probe:
            return True
        try:
            resp = requests.get(probe, timeout=0.35)
        except Exception:
            return False
        if resp.status_code != 200:
            return False
        if probe.endswith("/camera/healthz"):
            try:
                payload = resp.json()
                if isinstance(payload, dict) and "ok" in payload:
                    return bool(payload.get("ok"))
            except Exception:
                return False
        return True

    def _capture_loop(self) -> None:
        cap: Optional[Any] = None
        open_fail_count = 0

        while not self._stop_event.is_set():
            if cap is None or not cap.isOpened():
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass

                if self._is_http_camera_source() and not self._http_camera_ready():
                    open_fail_count += 1
                    if open_fail_count >= self._max_camera_wait_attempts:
                        if not self._camera_gave_up:
                            self._camera_gave_up = True
                            logger.warning(
                                "Camera source unavailable after %d attempts (%s); pausing capture retries",
                                self._max_camera_wait_attempts,
                                self.camera_source,
                            )
                        time.sleep(3.0)
                        if self._http_camera_ready():
                            open_fail_count = 0
                            self._camera_gave_up = False
                            logger.info("Camera source recovered: %s", self.camera_source)
                        continue
                    if open_fail_count == 1 or open_fail_count == self._max_camera_wait_attempts:
                        logger.info(
                            "Camera source not ready yet: %s (attempt=%d/%d), waiting...",
                            self.camera_source,
                            open_fail_count,
                            self._max_camera_wait_attempts,
                        )
                    time.sleep(1.0)
                    continue

                cap = cv2.VideoCapture(self.camera_source)
                if not cap.isOpened():
                    open_fail_count += 1
                    if open_fail_count >= self._max_camera_wait_attempts:
                        if not self._camera_gave_up:
                            self._camera_gave_up = True
                            logger.warning(
                                "Could not open camera source after %d attempts: %s; pausing retries",
                                self._max_camera_wait_attempts,
                                self.camera_source,
                            )
                        time.sleep(3.0)
                        open_fail_count = 0
                        continue
                    if open_fail_count == 1 or open_fail_count == self._max_camera_wait_attempts:
                        logger.warning(
                            "Could not open camera source: %s (attempt=%d/%d), retrying...",
                            self.camera_source,
                            open_fail_count,
                            self._max_camera_wait_attempts,
                        )
                    time.sleep(1.0)
                    continue

                open_fail_count = 0
                logger.info("Camera source connected: %s", self.camera_source)

            ok, frame = cap.read()
            if not ok or frame is None:
                logger.warning("Failed to read frame, reconnecting camera source...")
                time.sleep(0.6)
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
                continue

            with self._frame_lock:
                self._latest_raw_frame = frame

            time.sleep(0.003)

        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

    def _inference_loop(self) -> None:
        while not self._stop_event.is_set():
            frame = None
            with self._frame_lock:
                if self._latest_raw_frame is not None:
                    frame = self._latest_raw_frame.copy()

            if frame is None:
                time.sleep(0.08)
                continue

            parsed_results, annotated = self._analyze_frame(frame, enable_follow=True)
            if self._onsensor_active():
                extras = self._onsensor_object_results()
                if extras:
                    parsed_results = list(parsed_results) + extras
            self.latest_results = parsed_results

            # Continuous "living vision": let the sampler decide when to refresh
            # the richer VLM scene context (idle cadence + scene-change driven).
            self._maybe_sample_vlm(parsed_results)

            # Follow aktifken VLM sahne aksiyonu / tehlike anonsu bastirilir,
            # odak yuz kilidi ve takip akisinda kalir.
            self._handle_person_interactions(parsed_results)
            if not self._follow_active:
                self._evaluate_alerts(parsed_results)
                if parsed_results and self.mode_flags.get("semantic_scene", True):
                    self.action_dispatcher.emit_scene(self.semantic, parsed_results)
                if self.blind_mode_enabled and parsed_results:
                    self._handle_blind_mode(parsed_results)

            ok, buf = cv2.imencode(".jpg", annotated)
            if ok:
                with self._frame_lock:
                    self._latest_annotated_frame = buf.tobytes()

            time.sleep(0.05)

    # -----------------------------------------------------------------
    # Living-vision sampling
    # -----------------------------------------------------------------
    @staticmethod
    def _scene_signature(parsed_results: List[Dict[str, Any]]) -> frozenset:
        sig = set()
        for r in parsed_results or []:
            if isinstance(r, dict):
                sig.add((str(r.get("label", "")), str(r.get("name", ""))))
        return frozenset(sig)

    def _scene_change_score(self, parsed_results: List[Dict[str, Any]]) -> float:
        sig = self._scene_signature(parsed_results)
        prev = getattr(self, "_last_scene_signature", None)
        self._last_scene_signature = sig
        if prev is None:
            return 0.0
        union = prev | sig
        if not union:
            return 0.0
        churn = prev ^ sig
        return len(churn) / len(union)

    def _maybe_sample_vlm(self, parsed_results: List[Dict[str, Any]]) -> None:
        sampler = getattr(self, "vision_sampler", None)
        if sampler is None:
            return
        if getattr(self, "_vlm_refresh_inflight", False):
            return
        score = self._scene_change_score(parsed_results)
        try:
            should = sampler.should_call_vlm(
                scene_change_score=score,
                follow_mode_active=bool(getattr(self, "_follow_active", False)),
            )
        except Exception:
            return
        if not should:
            return
        sampler.record_call()
        self._vlm_refresh_inflight = True
        threading.Thread(target=self._background_context_refresh, daemon=True).start()

    def _background_context_refresh(self) -> None:
        try:
            context = self.refresh_visual_context()
            if context is not None and self.event_bus is not None:
                self.event_bus.publish(EVENT_SCENE_CHANGED, {"context": context})
                self.event_bus.publish(EVENT_VLM_RESULT_READY, {"context": context})
        except Exception:
            pass
        finally:
            self._vlm_refresh_inflight = False

    # -----------------------------------------------------------------
    # Core analysis
    # -----------------------------------------------------------------
    def _analyze_frame(self, frame: Any, enable_follow: bool) -> Tuple[List[Dict[str, Any]], Any]:
        boxes: List[Tuple[int, int, int, int]] = []
        tracked_box = None
        onsensor_active = self._onsensor_active()

        if enable_follow and self._follow_active:
            tracked_box = self._update_tracker(frame)
            if tracked_box is not None:
                boxes = [tracked_box]
            else:
                if onsensor_active:
                    boxes = self._onsensor_boxes_for_label(frame.shape, "person")
                if not boxes:
                    boxes = self._detect_face_boxes(frame)
        else:
            if onsensor_active:
                boxes = self._onsensor_boxes_for_label(frame.shape, "person")
            if not boxes:
                boxes = self._detect_face_boxes(frame)

        parsed: List[Dict[str, Any]] = []
        annotated = frame.copy()
        for idx, bbox in enumerate(boxes):
            x1, y1, x2, y2 = bbox
            if x2 <= x1 or y2 <= y1:
                continue
            face_roi = frame[y1:y2, x1:x2]
            name = "Unknown"
            conf = 0.5
            if self.face_manager is not None:
                try:
                    if hasattr(self.face_manager, "identify_face_with_score"):
                        name, score = self.face_manager.identify_face_with_score(face_roi)
                        conf = max(0.0, min(1.0, float(score)))
                    else:
                        name = self.face_manager.identify_face(face_roi)
                        conf = 0.9 if name != "Unknown" else 0.5
                except Exception as exc:
                    logger.debug("face identify failed: %s", exc)

            distance = self._estimate_face_distance_m(y2 - y1)
            tracked = bool(tracked_box is not None and idx == 0)
            parsed.append(
                {
                    "label": "person",
                    "confidence": round(conf, 3),
                    "bbox": [x1, y1, x2, y2],
                    "distance_m": distance,
                    "name": name,
                    "tracked": tracked,
                }
            )

            color = (0, 220, 0)
            if name != "Unknown":
                color = (255, 100, 40)
            if tracked:
                color = (60, 180, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = name if name != "Unknown" else "person"
            tag = f"{label} {conf:.2f}"
            if distance is not None:
                tag += f" {distance:.1f}m"
            if tracked:
                tag += " [CSRT]"
            cv2.putText(
                annotated,
                tag,
                (x1, max(14, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
            )

        if enable_follow and self._follow_active:
            if self._follow_tracker is None and parsed:
                self._lock_tracker_from_candidates(frame, parsed)
            self._drive_follow(parsed, frame.shape)

        if not self.mode_flags.get("people", True):
            parsed = []
        elif not self.mode_flags.get("faces", True):
            for item in parsed:
                item["name"] = "Unknown"

        return parsed, annotated

    def _detect_face_boxes(self, frame: Any) -> List[Tuple[int, int, int, int]]:
        if self._face_cascade is None or self._face_cascade.empty():
            return []
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            faces = self._face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.12,
                minNeighbors=5,
                minSize=(56, 56),
            )
        except Exception:
            return []

        out: List[Tuple[int, int, int, int]] = []
        h, w = frame.shape[:2]
        for (x, y, fw, fh) in faces:
            x1 = _clamp(int(x), 0, w - 1)
            y1 = _clamp(int(y), 0, h - 1)
            x2 = _clamp(int(x + fw), 0, w)
            y2 = _clamp(int(y + fh), 0, h)
            if x2 > x1 and y2 > y1:
                out.append((x1, y1, x2, y2))
        return out

    def _estimate_face_distance_m(self, box_h: int) -> Optional[float]:
        # Basit pinhole tahmini (yaklasik): face_h_real~0.24m, focal_px~600
        if box_h <= 0:
            return None
        distance = (0.24 * 600.0) / float(box_h)
        return round(float(distance), 2)

    def _update_tracker(self, frame: Any) -> Optional[Tuple[int, int, int, int]]:
        if self._follow_tracker is None:
            return None
        try:
            ok, box = self._follow_tracker.update(frame)
        except Exception:
            ok, box = False, None

        if not ok or box is None:
            self._follow_lost_frames += 1
            if self._follow_lost_frames >= int(self._follow_cfg.get("max_lost_frames", 18)):
                self._follow_tracker = None
                self._follow_current_bbox = None
            return None

        self._follow_lost_frames = 0
        x, y, w, h = [int(v) for v in box]
        x1, y1, x2, y2 = x, y, x + w, y + h
        self._follow_current_bbox = (x1, y1, x2, y2)
        return self._follow_current_bbox

    def _lock_tracker_from_candidates(self, frame: Any, results: List[Dict[str, Any]]) -> None:
        target_idx = 0
        target_name = str(self._follow_target or "").strip().lower()
        if target_name:
            for i, res in enumerate(results):
                name = str(res.get("name") or "").strip().lower()
                if name and name == target_name:
                    target_idx = i
                    break
        else:
            for i, res in enumerate(results):
                if str(res.get("name") or "") not in ("", "Unknown"):
                    target_idx = i
                    break

        bbox = results[target_idx].get("bbox") or []
        if len(bbox) != 4:
            return
        x1, y1, x2, y2 = [int(v) for v in bbox]
        tracker = _create_csrt_tracker()
        if tracker is None:
            return

        try:
            ok = tracker.init(frame, (x1, y1, x2 - x1, y2 - y1))
        except Exception:
            ok = False
        if not ok:
            return

        self._follow_tracker = tracker
        self._follow_lost_frames = 0
        self._follow_current_bbox = (x1, y1, x2, y2)

    def _drive_follow(self, results: List[Dict[str, Any]], frame_shape: Tuple[int, ...]) -> None:
        if not self._follow_active or not results:
            return

        now = time.time()
        if now - self._follow_last_track_ts < float(self._follow_cfg.get("track_interval_s", 0.12)):
            return

        # Takipte once tracker bbox, yoksa secili hedef kisinin bbox'i kullanilir.
        selected = None
        if self._follow_current_bbox is not None:
            for res in results:
                b = res.get("bbox") or []
                if len(b) == 4 and tuple(int(v) for v in b) == self._follow_current_bbox:
                    selected = res
                    break
        if selected is None:
            target = str(self._follow_target or "").strip().lower()
            if target:
                for res in results:
                    name = str(res.get("name") or "").strip().lower()
                    if name == target:
                        selected = res
                        break
        if selected is None:
            selected = results[0]

        bbox = selected.get("bbox") or []
        if len(bbox) != 4:
            return
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame_shape[:2]
        cx = (x1 + x2) * 0.5
        cy = (y1 + y2) * 0.5

        dx_norm = ((cx - (w * 0.5)) / max(1.0, w * 0.5))
        dy_norm = ((cy - (h * 0.5)) / max(1.0, h * 0.5))

        pan = int(round(float(self._follow_cfg.get("center_pan", 90)) + dx_norm * float(self._follow_cfg.get("pan_gain_deg", 50.0))))
        tilt = int(round(float(self._follow_cfg.get("center_tilt", 90)) + dy_norm * float(self._follow_cfg.get("tilt_gain_deg", 32.0))))

        pan = _clamp(pan, int(self._follow_cfg.get("min_pan", 35)), int(self._follow_cfg.get("max_pan", 145)))
        tilt = _clamp(tilt, int(self._follow_cfg.get("min_tilt", 65)), int(self._follow_cfg.get("max_tilt", 125)))

        if self.head_arbiter is not None and HeadCommand is not None:
            source = "owner_follow" if str(self._follow_target or "").lower() in {"owner", "emir"} else "active_speaker"
            priority = 85 if source == "owner_follow" else 75
            self.head_arbiter.request_move(
                HeadCommand(pan=float(pan), tilt=float(tilt), source=source, priority=priority, ttl_s=1.0)
            )
        else:
            self._send_track(pan=pan, tilt=tilt, drive=0)
        self._follow_last_track_ts = now

    def _send_track(self, pan: int, tilt: int, drive: int = 0) -> None:
        if self._track_callback is not None:
            try:
                self._track_callback(head_pan=float(pan), head_tilt=float(tilt), drive=int(drive))
                return
            except Exception as exc:
                logger.debug("track callback failed: %s", exc)

        try:
            from modules.gateway.url import gateway_url

            requests.post(
                gateway_url(self._gateway_base, "/vlm/track"),
                params={"head_pan": float(pan), "head_tilt": float(tilt), "drive": int(drive)},
                timeout=0.25,
            )
        except Exception:
            pass

    # -----------------------------------------------------------------
    # API-compatible helpers
    # -----------------------------------------------------------------
    def generate_frames(self) -> Generator[bytes, None, None]:
        while True:
            frame = None
            with self._frame_lock:
                frame = self._latest_annotated_frame

            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            time.sleep(0.05)

    def analyze_snapshot(self) -> List[Dict[str, Any]]:
        if self.processing_mode != "local":
            return [{"error": "Local analysis disabled in remote mode"}]

        if self._is_http_camera_source():
            frame = None
            with self._frame_lock:
                if self._latest_raw_frame is not None:
                    frame = self._latest_raw_frame.copy()
            if frame is None:
                return [{"error": "No frame available yet"}]
            results, _annotated = self._analyze_frame(frame, enable_follow=False)
            return results

        cap = cv2.VideoCapture(self.camera_source)
        if not cap.isOpened():
            return [{"error": "Could not open camera"}]
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return [{"error": "Failed to capture frame"}]

        results, _annotated = self._analyze_frame(frame, enable_follow=False)
        return results

    def register_face_from_current_frame(self, name: str) -> bool:
        if not self.face_manager or self.processing_mode != "local":
            return False
        frame = None
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                frame = self._latest_raw_frame.copy()
        if frame is None and not self._is_http_camera_source():
            try:
                cap = cv2.VideoCapture(self.camera_source)
                if cap.isOpened():
                    ok, snap = cap.read()
                    cap.release()
                    if ok and snap is not None:
                        frame = snap
            except Exception:
                pass
        if frame is None:
            return False
        return bool(self.face_manager.register_face(name, frame))

    # -----------------------------------------------------------------
    # Remote ingestion
    # -----------------------------------------------------------------
    def ingest_remote_results(self, objects: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Follow modunda uzak VLM nesne akisi bastirilir.
        if self._follow_active:
            return {"count": 0, "skipped": "follow_active"}

        normalized: List[Dict[str, Any]] = []
        for o in objects:
            if not isinstance(o, dict):
                continue
            label = o.get("label") or o.get("name") or "unknown"
            conf = float(o.get("confidence", o.get("conf", 0.0)) or 0.0)
            bbox = o.get("bbox") or o.get("box") or []
            distance = o.get("distance_m") if o.get("distance_m") is not None else o.get("distance")
            normalized.append(
                {
                    "label": label,
                    "confidence": conf,
                    "bbox": bbox,
                    "distance_m": distance,
                    "name": o.get("name", "Unknown"),
                }
            )

        if not self.mode_flags.get("objects", True):
            normalized = [r for r in normalized if str(r.get("label", "")).lower() == "person"]
        if not self.mode_flags.get("people", True):
            normalized = [r for r in normalized if str(r.get("label", "")).lower() != "person"]
        if not self.mode_flags.get("faces", True):
            for item in normalized:
                item["name"] = "Unknown"

        self.latest_results = normalized
        self._evaluate_alerts(normalized)
        self._handle_person_interactions(normalized)
        if self.blind_mode_enabled and normalized:
            self._handle_blind_mode(normalized)
        if normalized and self.mode_flags.get("semantic_scene", True):
            self.action_dispatcher.emit_scene(self.semantic, normalized)
        return {"count": len(normalized)}

    def record_chat(self, person: str, text: str, role: str = "assistant") -> None:
        self.memory.append_chat(person, role, text)

    # -----------------------------------------------------------------
    # Living Vision Agent: Context and VLM Integration
    # -----------------------------------------------------------------

    def attach_onsensor_bus(self, bus: Any) -> None:
        """Subscribe to an on-sensor (IMX500) event bus.

        The processor caches the most recent snapshot and prefers IMX500 boxes
        over Haar when ``mode_categories.onsensor.tiny_detect`` is enabled.
        """
        if bus is None:
            return
        if self._onsensor_unsub is not None:
            try:
                self._onsensor_unsub()
            except Exception:
                pass
            self._onsensor_unsub = None
        self._onsensor_bus = bus
        if hasattr(bus, "subscribe"):
            try:
                self._onsensor_unsub = bus.subscribe(self._on_sensor_snapshot)
            except Exception as exc:
                logger.debug("onsensor subscribe failed: %s", exc)

    def detach_onsensor_bus(self) -> None:
        if self._onsensor_unsub is not None:
            try:
                self._onsensor_unsub()
            except Exception:
                pass
            self._onsensor_unsub = None
        self._onsensor_bus = None

    def _on_sensor_snapshot(self, snapshot: Any) -> None:
        with self._onsensor_lock:
            self._latest_onsensor = snapshot

    def _latest_onsensor_snapshot(self) -> Optional[Any]:
        with self._onsensor_lock:
            return self._latest_onsensor

    def _onsensor_active(self) -> bool:
        if self._onsensor_bus is None:
            return False
        flags = self.mode_categories.get("onsensor", {})
        return bool(flags.get("tiny_detect", False))

    def _onsensor_boxes_for_label(self, frame_shape: Tuple[int, ...], label: str) -> List[Tuple[int, int, int, int]]:
        snap = self._latest_onsensor_snapshot()
        if snap is None:
            return []
        max_age = 1.5
        try:
            if (time.time() - float(getattr(snap, "ts", 0.0))) > max_age:
                return []
        except Exception:
            return []
        h, w = frame_shape[:2]
        boxes: List[Tuple[int, int, int, int]] = []
        for det in getattr(snap, "detections", []) or []:
            if str(getattr(det, "label", "")).strip().lower() != label.strip().lower():
                continue
            bbox = getattr(det, "bbox_xyxy_norm", None)
            if not bbox or len(bbox) != 4:
                continue
            x1n, y1n, x2n, y2n = [float(v) for v in bbox]
            if max(x2n, y2n) <= 1.5:
                x1 = int(_clamp(int(x1n * w), 0, w - 1))
                y1 = int(_clamp(int(y1n * h), 0, h - 1))
                x2 = int(_clamp(int(x2n * w), 0, w))
                y2 = int(_clamp(int(y2n * h), 0, h))
            else:
                x1 = int(_clamp(int(x1n), 0, w - 1))
                y1 = int(_clamp(int(y1n), 0, h - 1))
                x2 = int(_clamp(int(x2n), 0, w))
                y2 = int(_clamp(int(y2n), 0, h))
            if x2 > x1 and y2 > y1:
                boxes.append((x1, y1, x2, y2))
        return boxes

    def _onsensor_object_results(self) -> List[Dict[str, Any]]:
        snap = self._latest_onsensor_snapshot()
        if snap is None:
            return []
        results: List[Dict[str, Any]] = []
        for det in getattr(snap, "detections", []) or []:
            label = str(getattr(det, "label", "")).strip()
            if not label or label.lower() == "person":
                continue
            bbox = list(getattr(det, "bbox_xyxy_norm", []) or [])
            results.append(
                {
                    "label": label,
                    "confidence": float(getattr(det, "score", 0.0) or 0.0),
                    "bbox": bbox,
                    "distance_m": None,
                    "name": "",
                    "source": "imx500",
                }
            )
        return results

    def _grab_frame(self) -> Optional[Any]:
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                return self._latest_raw_frame.copy()
        if self._is_http_camera_source():
            return None
        try:
            cap = cv2.VideoCapture(self.camera_source)
            if cap.isOpened():
                ok, snap = cap.read()
                cap.release()
                if ok and snap is not None:
                    return snap
        except Exception:
            pass
        return None

    def _encode_frame_b64(self, frame: Any, quality: int = 80) -> Optional[str]:
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
            if not ok:
                return None
            return base64.b64encode(buf.tobytes()).decode("ascii")
        except Exception:
            return None

    def run_ocr_remote(self, frame: Optional[Any] = None, languages: Optional[List[str]] = None) -> Dict[str, Any]:
        """Forward an OCR request to the remote multimodal server.

        Pulls the latest frame if ``frame`` is not provided. Returns a JSON-able
        dict that mirrors the remote ``/vision/ocr`` response, with explicit
        ``ok`` and ``error`` fields when the remote backend is disabled.
        """
        if not self.mode_categories.get("remote", {}).get("ocr", False) and not self.mode_flags.get("ocr", False):
            return {"ok": False, "error": "ocr_mode_disabled"}
        if not self.remote_mm_enabled:
            return {"ok": False, "error": "remote_multimodal_disabled"}
        endpoint = self.remote_mm_ocr_endpoint
        if not endpoint:
            return {"ok": False, "error": "remote_ocr_endpoint_missing"}

        target_frame = frame if frame is not None else self._grab_frame()
        if target_frame is None:
            return {"ok": False, "error": "no_frame_available"}
        image_b64 = self._encode_frame_b64(target_frame, quality=80)
        if not image_b64:
            return {"ok": False, "error": "frame_encode_failed"}

        langs = languages or self.remote_mm_ocr_languages
        payload: Dict[str, Any] = {"image_b64": image_b64}
        if langs:
            payload["languages"] = list(langs)
        headers: Dict[str, str] = {}
        if self.remote_mm_auth_token:
            headers["X-Auth-Token"] = self.remote_mm_auth_token
        try:
            resp = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=self.remote_mm_ocr_timeout_s,
            )
        except Exception as exc:
            return {"ok": False, "error": f"remote_call_failed: {exc}"}
        if resp.status_code != 200:
            return {"ok": False, "error": f"remote_http_{resp.status_code}"}
        try:
            data = resp.json()
        except Exception as exc:
            return {"ok": False, "error": f"remote_json_failed: {exc}"}
        if not isinstance(data, dict):
            return {"ok": False, "error": "remote_payload_invalid"}
        data.setdefault("ok", True)
        return data

    def _remote_requested_tasks(self) -> List[str]:
        remote = self.mode_categories.get("remote", {})
        tasks: List[str] = []
        for key in ("objects", "people", "faces", "ocr", "hazards", "semantic_scene", "depth"):
            if bool(remote.get(key, False)):
                tasks.append(key)
        return tasks

    def _call_remote_multimodal(self, frame: Any) -> Optional[Dict[str, Any]]:
        if not self.remote_mm_enabled or not self.remote_mm_endpoint:
            return None
        try:
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                return None
            image_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            payload: Dict[str, Any] = {"image_b64": image_b64}
            requested = self._remote_requested_tasks()
            if requested:
                payload["requested_tasks"] = requested
            headers = {}
            if self.remote_mm_auth_token:
                headers["X-Auth-Token"] = self.remote_mm_auth_token
            resp = requests.post(
                self.remote_mm_endpoint,
                json=payload,
                headers=headers,
                timeout=self.remote_mm_timeout_s,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if isinstance(data, dict):
                return data
        except Exception as exc:
            logger.debug("remote multimodal call failed: %s", exc)
        return None

    def _context_from_remote_multimodal(self, mm: Dict[str, Any], question: str = "") -> Dict[str, Any]:
        people = list(mm.get("people", []) or [])
        objects = list(mm.get("objects", []) or [])
        hazards = list(mm.get("hazards", []) or [])
        summary = str(mm.get("summary", "")).strip()
        interpretation = str(mm.get("persona_interpretation", "")).strip() or summary
        importance = float(mm.get("importance_score", 0.55 if hazards else 0.4))
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": summary,
            "objects": objects,
            "people": people,
            "hazards": hazards,
            "interesting_events": list(mm.get("interesting_events", []) or []),
            "recommended_focus": dict(mm.get("recommended_focus", {}) or {}),
            "importance_score": min(1.0, max(0.0, importance + (0.1 if question else 0.0))),
            "raw_vlm_observation": str(mm.get("raw_text", "")),
            "persona_interpretation": interpretation,
        }

    def get_latest_visual_context(self) -> Optional[Dict[str, Any]]:
        """Return the latest cached visual context (if available)."""
        if self.visual_context_cache is None:
            return None
        if self.visual_context_cache.age_s > self._context_max_age_s:
            return None
        ctx = self.visual_context_cache.get_latest()
        if ctx is None:
            fallback = self._build_context_from_results(self.latest_results)
            if fallback is None:
                return None
            self.update_visual_context(fallback)
            ctx = self.visual_context_cache.get_latest()
            if ctx is None:
                return None
        return ctx.to_dict()

    def refresh_visual_context(self, question: str = "") -> Optional[Dict[str, Any]]:
        """Capture/refresh the latest context using VLM when possible."""
        frame = None
        with self._frame_lock:
            if self._latest_raw_frame is not None:
                frame = self._latest_raw_frame.copy()

        # 1) Preferred path: remote multimodal server (PC-side inference stack)
        if frame is not None and self.remote_mm_enabled:
            mm_result = self._call_remote_multimodal(frame)
            if isinstance(mm_result, dict) and mm_result.get("ok", True):
                context = self._context_from_remote_multimodal(mm_result, question=question)
                self.update_visual_context(context)
                # Keep latest_results in sync so existing flows continue to work.
                merged_results = []
                for p in context.get("people", []):
                    if isinstance(p, dict):
                        merged_results.append(
                            {
                                "label": "person",
                                "name": p.get("name", "Unknown"),
                                "confidence": float(p.get("confidence", 0.0) or 0.0),
                                "bbox": p.get("bbox", []),
                                "distance_m": p.get("distance_m"),
                            }
                        )
                for o in context.get("objects", []):
                    if isinstance(o, dict):
                        merged_results.append(o)
                if merged_results:
                    self.latest_results = merged_results
                latest = self.get_latest_visual_context()
                if latest is not None:
                    return latest

        if frame is not None and self.vlm_client is not None:
            vlm_result = self.vlm_client.analyze_frame(frame, force=bool(question))
            if isinstance(vlm_result, dict):
                context = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "summary": str(vlm_result.get("summary", "")),
                    "objects": list(vlm_result.get("objects", []) or []),
                    "people": list(vlm_result.get("people", []) or []),
                    "hazards": list(vlm_result.get("hazards", []) or []),
                    "interesting_events": list(vlm_result.get("interesting", []) or vlm_result.get("interesting_events", []) or []),
                    "recommended_focus": dict(vlm_result.get("recommended_focus", {}) or {}),
                    "importance_score": 0.6 if question else 0.4,
                    "raw_vlm_observation": str(vlm_result.get("raw_text", "")),
                    "persona_interpretation": str(vlm_result.get("summary", "")),
                }
                self.update_visual_context(context)
                latest = self.get_latest_visual_context()
                if latest is not None:
                    return latest

        fallback = self._build_context_from_results(self.latest_results)
        if fallback is not None:
            self.update_visual_context(fallback)
            return self.get_latest_visual_context()
        return None

    def _build_context_from_results(self, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not results:
            return None
        people = []
        objects = []
        for item in results:
            if str(item.get("label", "")).lower() == "person":
                people.append(
                    {
                        "track_id": "",
                        "person_id": "",
                        "name": item.get("name", "Unknown"),
                        "recognition_level": 0 if item.get("name", "Unknown") == "Unknown" else 2,
                        "relationship": "unknown",
                        "confidence": float(item.get("confidence", 0.0) or 0.0),
                        "bbox": list(item.get("bbox", [0, 0, 0, 0])),
                        "distance_m": item.get("distance_m"),
                        "gaze_priority": 0.4,
                        "last_seen": datetime.utcnow().isoformat(),
                        "is_follow_target": bool(item.get("tracked", False)),
                        "appearance_notes": "",
                    }
                )
            else:
                objects.append(item)
        summary = f"{len(people)} kişi ve {len(objects)} nesne algılandı."
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": summary,
            "objects": objects,
            "people": people,
            "hazards": [],
            "interesting_events": [],
            "recommended_focus": {"type": "person" if people else "none", "target_id": "", "reason": "latest_detection"},
            "importance_score": 0.5 if people else 0.3,
            "raw_vlm_observation": summary,
            "persona_interpretation": summary,
        }

    def update_visual_context(self, context: Optional[Dict[str, Any]]) -> None:
        """Update the cached visual context (typically called by VLM after processing)."""
        if self.visual_context_cache is None or context is None:
            return
        try:
            # Reconstruct from dict if needed
            if hasattr(self.visual_context_cache, 'set_context'):
                self.visual_context_cache.set_context(context)
            else:
                # Direct assignment if it's a VisualContextCache
                from .visual_context import VisionFrameContext, PersonContext
                vfc = VisionFrameContext(
                    timestamp=context.get("timestamp", ""),
                    summary=context.get("summary", ""),
                    objects=context.get("objects", []),
                    people=[PersonContext(**p) if isinstance(p, dict) else p for p in context.get("people", [])],
                    hazards=context.get("hazards", []),
                    interesting_events=context.get("interesting_events", []),
                    recommended_focus=context.get("recommended_focus", {}),
                    importance_score=context.get("importance_score", 0.0),
                    raw_vlm_observation=context.get("raw_vlm_observation", ""),
                    persona_interpretation=context.get("persona_interpretation", ""),
                )
                self.visual_context_cache.update(vfc)
        except Exception as exc:
            logger.debug("Failed to update visual context: %s", exc)

    # -----------------------------------------------------------------
    # Interaction / alert layer
    # -----------------------------------------------------------------
    def _handle_blind_mode(self, results: List[Dict[str, Any]]) -> None:
        now = time.time()
        interval = float(self.config.get("vision", {}).get("blind_mode", {}).get("interval_seconds", 5.0))
        if now - self.last_blind_announcement < interval:
            return
        if not results:
            return

        text = self.semantic.describe(results)
        for r in results:
            name = r.get("name")
            if name and name != "Unknown":
                self.memory.set_summary(name, text)

        self._send_tts(text)
        self.last_blind_announcement = now

    def _send_tts(self, text: str) -> None:
        out_text = str(text or "")
        tcfg = self.config.get("translation", {}) if isinstance(self.config.get("translation", {}), dict) else {}
        if out_text and bool(tcfg.get("enabled", False)):
            endpoint = str(tcfg.get("endpoint", "http://localhost:8080/ollama/translate"))
            source_lang = str(tcfg.get("source_lang", "auto"))
            target_lang = str(tcfg.get("target_lang", "tr"))
            timeout = float(tcfg.get("timeout", 1.5))
            try:
                resp = requests.post(
                    endpoint,
                    params={"text": out_text, "source_lang": source_lang, "target_lang": target_lang},
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("ok") and data.get("text"):
                        out_text = str(data.get("text"))
            except Exception as exc:
                logger.debug("vlm_bridge translation failed: %s", exc)

        url = self.config.get("speak", {}).get("endpoint") or "http://localhost:8083/speak/say"
        try:
            requests.post(url, json={"text": out_text}, timeout=1.0)
        except Exception as exc:
            logger.debug("Failed to send TTS: %s", exc)

    def _evaluate_alerts(self, results: List[Dict[str, Any]]) -> None:
        vision_cfg = self.config.get("vision", {})
        alerts_cfg = vision_cfg.get("alerts", {})
        if not alerts_cfg or not self.mode_flags.get("hazards", True):
            return

        classes = {str(c) for c in alerts_cfg.get("classes", [])}
        dist_thr = float(alerts_cfg.get("distance_threshold_m", 1.0))
        announce_interval = float(alerts_cfg.get("announce_interval_s", 10.0))
        now = time.time()
        if now - self.last_alert_announcement < announce_interval:
            return

        hazards = []
        for r in results:
            lbl = str(r.get("label") or "")
            dist = r.get("distance_m")
            if lbl in classes and isinstance(dist, (int, float)) and float(dist) <= dist_thr:
                hazards.append((lbl, float(dist)))
        if not hazards:
            return

        parts = [f"{lbl} {dist:.1f}m" for lbl, dist in hazards]
        self._send_tts("Dikkat yakın tehlike: " + ", ".join(parts))
        self._emit_emotion("alert")
        if self.event_bus is not None:
            self.event_bus.publish(EVENT_HAZARD_DETECTED, {"hazards": parts})
        self.last_alert_announcement = now

    def _emit_emotion(self, emotion: str) -> None:
        try:
            from modules.gateway.url import gateway_url

            requests.post(
                gateway_url(self._gateway_base, "/interactions/event"),
                json={"type": f"autonomy.{emotion}"},
                timeout=0.5,
            )
        except Exception:
            pass

    def _handle_person_interactions(self, results: List[Dict[str, Any]]) -> None:
        vision_cfg = self.config.get("vision", {})
        if not self.mode_flags.get("people", True):
            return

        greet_cooldown = float(vision_cfg.get("personalization", {}).get("greet_cooldown_s", 30))
        now = time.time()
        for r in results:
            name = r.get("name")
            if not name or name == "Unknown":
                continue
            if self.person_identity is not None:
                rec = self.person_identity.recognize(
                    name=str(name),
                    confidence=float(r.get("confidence", 0.0) or 0.0),
                    face_score=float(r.get("confidence", 0.0) or 0.0),
                )
                r["person_id"] = rec.person_id
                r["recognition_level"] = rec.recognition_level
                r["relationship"] = rec.relationship
                if rec.recognition_level >= 5 and self.event_bus is not None:
                    self.event_bus.publish(EVENT_OWNER_SEEN, {"name": rec.name, "person_id": rec.person_id})
                elif rec.seen_count <= 2 and self.event_bus is not None:
                    self.event_bus.publish(EVENT_NEW_PERSON, {"name": rec.name, "person_id": rec.person_id})
            last = self._last_person_greet.get(name, 0.0)
            if now - last < greet_cooldown:
                continue

            greeting = self._build_greeting(name)
            if greeting:
                self._send_tts(greeting)
            self._emit_emotion("excited")
            self.memory.append_chat(name, role="system", text=f"Greeted: {greeting}")

            follow = self._ollama_followup(name)
            if follow:
                self._send_tts(follow)
                self.memory.append_chat(name, role="assistant", text=follow)

            self._last_person_greet[name] = now

    def _build_greeting(self, name: str) -> Optional[str]:
        p_cfg = self.config.get("vision", {}).get("personalization", {})
        known = p_cfg.get("known_people", {})
        if name in known:
            return known[name].get("greeting")
        return f"Merhaba {name}, seni gordugume sevindim."

    def _ollama_followup(self, name: str) -> Optional[str]:
        rec = self.memory.get_person(name) or {}
        last_sum = (rec.get("last_summary") or {}).get("text")
        prompt = (
            f"{name} ile karsilastin. {('Ozet: ' + last_sum) if last_sum else ''} "
            "Turkce sicak ve dogal bir karsilama yap. 2 cumle kur; "
            "ilk cumle samimi selamlama, ikinci cumle baglama uygun kisa bir takip sorusu olsun."
        )
        llm_cfg = self.config.get("ollama", {}) if isinstance(self.config.get("ollama", {}), dict) else {}
        timeout = float(llm_cfg.get("timeout", 4.0))
        return generate_text(prompt, llm_cfg, timeout=timeout, response_lang="tr")
