from __future__ import annotations

VLM_PROCESSOR_LEGACY_COMPATIBILITY_CONTRACT = True
VLM_PROCESSOR_LEGACY_COMPATIBILITY_ROLE = "opencv_api_and_cached_context_compatibility"

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

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

import requests

from .processor_follow import ProcessorFollowMixin, _clamp
from .processor_identity import ProcessorIdentityMixin
from .processor_modes import ProcessorModesMixin
from .processor_stream import ProcessorStreamMixin
from .processor_vlm import ProcessorVlmMixin
from .processor_init import ProcessorInitMixin

logger = logging.getLogger("vlm_bridge")


def _create_csrt_tracker() -> Optional[Any]:
    active_cv2 = globals().get("cv2")
    if active_cv2 is None:
        return None
    if hasattr(active_cv2, "TrackerCSRT_create"):
        try:
            return active_cv2.TrackerCSRT_create()
        except Exception:
            pass
    legacy = getattr(active_cv2, "legacy", None)
    if legacy is not None and hasattr(legacy, "TrackerCSRT_create"):
        try:
            return legacy.TrackerCSRT_create()
        except Exception:
            pass
    return None


class VisionProcessor(
    ProcessorInitMixin,
    ProcessorFollowMixin,
    ProcessorIdentityMixin,
    ProcessorVlmMixin,
    ProcessorModesMixin,
    ProcessorStreamMixin,
):
    """YOLO'suz VLM Bridge isleyici.

    Yerelde:
    - OpenCV Haar face detect
    - OpenCV ORB+FLANN ile kimliklendirme
    - CSRT ile takip

    Uzakta:
    - /vlm/results ile gelen sonuclari cache'ler.
    """

    def __init__(self, config: Dict[str, Any]):
        self._init_vision_processor(config)


    def _ensure_face_manager(self) -> None:
        if self.face_manager is not None or FaceManager is None:
            return
        if self.processing_mode != "local":
            return
        try:
            vision_cfg = self.config.get("vision", {}) if isinstance(self.config.get("vision"), dict) else {}
            face_match_cfg = (
                vision_cfg.get("face_match", {}) if isinstance(vision_cfg.get("face_match"), dict) else {}
            )
            self.face_manager = FaceManager(
                ratio_test=float(face_match_cfg.get("ratio_test", 0.72)),
                min_good_matches=int(face_match_cfg.get("min_good_matches", 10)),
                min_score=float(face_match_cfg.get("min_score", 0.15)),
            )
            logger.info("FaceManager lazy-initialized for local processing mode")
        except Exception as exc:
            logger.warning("FaceManager lazy init failed: %s", exc)

    def ingest_remote_results(self, objects: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                    "emotion": str(o.get("emotion") or o.get("face_emotion") or "").strip(),
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
        self._maybe_sample_vlm(normalized)
        if self.blind_mode_enabled and normalized:
            self._handle_blind_mode(normalized)
        if normalized and self.mode_flags.get("semantic_scene", True):
            self.action_dispatcher.emit_scene(self.semantic, normalized)
        return {"count": len(normalized)}

    def record_chat(self, person: str, text: str, role: str = "assistant") -> None:
        self.memory.append_chat(person, role, text)

    def run_ocr_remote(self, frame: Optional[Any] = None, languages: Optional[List[str]] = None) -> Dict[str, Any]:
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
