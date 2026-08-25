from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

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
    from modules.cognitive_memory.services.people_memory import PeopleMemory  # type: ignore

try:
    from .action_dispatcher import VisionActionDispatcher
except Exception:
    from modules.vlm_bridge.services.action_dispatcher import VisionActionDispatcher  # type: ignore

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
    from .vision_sampler import VisionSampler
except Exception:
    VisionSampler = None  # type: ignore

try:
    from .vision_request_gate import VisionRequestGate
except Exception:
    try:
        from modules.vlm_bridge.services.vision_request_gate import VisionRequestGate
    except Exception:
        VisionRequestGate = None  # type: ignore

try:
    from .face_emotion import FaceEmotionEstimator
except Exception:
    try:
        from modules.vlm_bridge.services.face_emotion import FaceEmotionEstimator
    except Exception:
        FaceEmotionEstimator = None  # type: ignore

try:
    from .vision_event_bus import VisionEventBus
except Exception:
    VisionEventBus = None  # type: ignore

try:
    from .head_control_arbiter import HeadControlArbiter
except Exception:
    HeadControlArbiter = None  # type: ignore

logger = logging.getLogger("vlm_bridge")


class ProcessorInitMixin:
    """Initialization mixin for VisionProcessor."""

    def _init_vision_processor(self, config: Dict[str, Any]) -> None:
        try:
            from modules.gateway.url import resolve_gateway_base_url, rewrite_loopback_urls

            self._gateway_base = resolve_gateway_base_url(config)
            config = rewrite_loopback_urls(config, self._gateway_base)
        except Exception:
            self._gateway_base = "http://127.0.0.1:8080"
        self.config = config
        vision_cfg = config.get("vision", {}) if isinstance(config, dict) else {}
        try:
            from .runtime_vision import apply_runtime_vision_profile

            vision_cfg = apply_runtime_vision_profile(vision_cfg if isinstance(vision_cfg, dict) else {})
        except Exception:
            vision_cfg = vision_cfg if isinstance(vision_cfg, dict) else {}

        self.processing_mode = str(vision_cfg.get("processing_mode", "local")).strip().lower()
        self.hybrid_local_capture = bool(vision_cfg.get("hybrid_local_capture", False))
        self._camera_hardware_available = False
        self.camera_source = vision_cfg.get("camera_source", 0)
        self._max_camera_wait_attempts = max(1, int(vision_cfg.get("max_camera_wait_attempts", 5)))
        self._camera_gave_up = False
        self._context_max_age_s = max(5.0, float(vision_cfg.get("context_max_age_s", 45.0)))
        self.conf_threshold = float(vision_cfg.get("confidence_threshold", 0.5))

        self.mode_flags = self._init_mode_flags(vision_cfg)
        self.mode_categories = self._init_mode_categories(vision_cfg, self.mode_flags)
        self._apply_aliases_and_disabled(vision_cfg)
        self.mode_profiles = self._init_mode_profiles(vision_cfg, self.mode_flags)

        self._face_cascade = load_frontal_face_cascade(logger)

        self.face_manager = None
        if FaceManager is not None:
            try:
                face_match_cfg = (
                    vision_cfg.get("face_match", {}) if isinstance(vision_cfg.get("face_match", {}), dict) else {}
                )
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
        self._follow_lock = threading.RLock()
        self._vlm_refresh_lock = threading.Lock()
        self._vlm_refresh_inflight = False
        self._latest_raw_frame: Optional[Any] = None
        self._latest_annotated_frame: Optional[bytes] = None

        self.latest_results: List[Dict[str, Any]] = []
        self.blind_mode_enabled = bool(vision_cfg.get("blind_mode", {}).get("enabled", False))
        self.last_blind_announcement = 0.0
        self.last_alert_announcement = 0.0
        self._last_person_greet: Dict[str, float] = {}
        self._visible_persons: set[str] = set()

        fer_cfg = dict(vision_cfg.get("face_emotion", {}) if isinstance(vision_cfg.get("face_emotion"), dict) else {})
        fer_cfg.setdefault("gateway_base_url", self._gateway_base)
        self._face_emotion = FaceEmotionEstimator(fer_cfg) if FaceEmotionEstimator is not None else None

        follow_cfg = vision_cfg.get("follow", {}) if isinstance(vision_cfg.get("follow"), dict) else {}
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
        self._follow_target = None
        self._follow_tracker = None
        self._follow_lost_frames = 0
        self._follow_last_track_ts = 0.0
        self._follow_current_bbox = None
        self._track_callback = None

        self.semantic = SemanticDescriber(config)
        self.memory = PeopleMemory()

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
            vctx_cfg = config.get("visual_context", {}) if isinstance(config.get("visual_context"), dict) else {}
            max_hist = max(1, int(vctx_cfg.get("cache_history_size", 5)))
            self.visual_context_cache = VisualContextCache(max_history=max_hist)
        else:
            self.visual_context_cache = None
            logger.warning("VisualContextCache not available")

        vlm_cfg = config.get("vision_llm", {}) if isinstance(config.get("vision_llm"), dict) else {}
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

        mm_cfg = config.get("remote_multimodal", {}) if isinstance(config.get("remote_multimodal"), dict) else {}
        self.remote_mm_enabled = bool(mm_cfg.get("enabled", False))
        self.remote_mm_endpoint = str(mm_cfg.get("endpoint", "http://127.0.0.1:8091/vision/analyze")).strip()
        default_cheap_endpoint = (
            self.remote_mm_endpoint.replace("/vision/analyze", "/vision/analyze/cheap")
            if self.remote_mm_endpoint
            else ""
        )
        default_semantic_endpoint = (
            self.remote_mm_endpoint.replace("/vision/analyze", "/vision/analyze/semantic")
            if self.remote_mm_endpoint
            else ""
        )
        self.remote_mm_cheap_endpoint = str(mm_cfg.get("cheap_endpoint", default_cheap_endpoint)).strip()
        self.remote_mm_semantic_endpoint = str(mm_cfg.get("semantic_endpoint", default_semantic_endpoint)).strip()
        self.remote_mm_timeout_s = float(mm_cfg.get("timeout_s", 6.0))
        self.remote_mm_auth_token = str(mm_cfg.get("auth_token", "")).strip()
        default_ocr_endpoint = (
            self.remote_mm_endpoint.replace("/vision/analyze", "/vision/ocr") if self.remote_mm_endpoint else ""
        )
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
        gate_cfg = (
            config.get("vision_request_gate", {}) if isinstance(config.get("vision_request_gate"), dict) else {}
        )
        self.vision_request_gate = (
            VisionRequestGate(gate_cfg, context_max_age_s=self._context_max_age_s)
            if VisionRequestGate is not None
            else None
        )
        self.vision_semantic_budget = self._init_semantic_budget(config)
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
