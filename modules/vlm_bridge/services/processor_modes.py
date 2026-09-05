from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vlm_bridge")


class ProcessorModesMixin:
    """Mode configurations, profiles, and runtime capabilities for VisionProcessor."""

    config: Dict[str, Any]
    processing_mode: str
    hybrid_local_capture: bool
    _camera_hardware_available: bool
    _camera_gave_up: bool
    mode_flags: Dict[str, bool]
    mode_categories: Dict[str, Dict[str, bool]]
    mode_profiles: Dict[str, Dict[str, bool]]
    _active_realtime_profile: str
    _realtime_profiles: Dict[str, Dict[str, Any]]
    _follow_cfg: Dict[str, Any]
    vlm_client: Any
    _frame_lock: Any
    _latest_raw_frame: Any
    _capture_thread: Any
    latest_results: List[Dict[str, Any]]

    @staticmethod
    def _init_mode_flags(vision_cfg: dict) -> Dict[str, bool]:
        raw_modes = vision_cfg.get("modes", {}) if isinstance(vision_cfg.get("modes"), dict) else {}
        return {
            "objects": bool(raw_modes.get("objects", True)),
            "people": bool(raw_modes.get("people", True)),
            "faces": bool(raw_modes.get("faces", True)),
            "depth": bool(raw_modes.get("depth", False)),
            "ocr": bool(raw_modes.get("ocr", False)),
            "hazards": bool(raw_modes.get("hazards", True)),
            "semantic_scene": bool(raw_modes.get("semantic_scene", True)),
        }

    @staticmethod
    def _init_mode_categories(vision_cfg: dict, mode_flags: dict) -> Dict[str, Dict[str, bool]]:
        raw_categories = (
            vision_cfg.get("mode_categories", {}) if isinstance(vision_cfg.get("mode_categories"), dict) else {}
        )

        def _bool_map(section: Dict[str, Any]) -> Dict[str, bool]:
            return {str(k): bool(v) for k, v in (section or {}).items()}

        return {
            "local": _bool_map(raw_categories.get("local", {"face_match": True, "visual_logger": True})),
            "remote": _bool_map(
                raw_categories.get(
                    "remote",
                    {
                        "objects": mode_flags["objects"],
                        "people": mode_flags["people"],
                        "faces": mode_flags["faces"],
                        "ocr": mode_flags["ocr"],
                        "hazards": mode_flags["hazards"],
                        "semantic_scene": mode_flags["semantic_scene"],
                        "depth": mode_flags["depth"],
                    },
                )
            ),
            "onsensor": _bool_map(raw_categories.get("onsensor", {"tiny_detect": False, "tiny_pose": False})),
        }

    def _apply_aliases_and_disabled(self, vision_cfg: dict) -> None:
        for alias_key in ("local_modes", "remote_modes", "onsensor_modes"):
            bucket_key = alias_key.replace("_modes", "")
            if bucket_key not in self.mode_categories:
                continue
            raw = vision_cfg.get(alias_key) or (
                vision_cfg.get("sensor_modes") if alias_key == "onsensor_modes" else None
            )
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key in self.mode_categories[bucket_key]:
                        self.mode_categories[bucket_key][key] = bool(value)
        disabled = vision_cfg.get("disabled_modes") or {}
        if isinstance(disabled, dict):
            for key, value in disabled.items():
                if not bool(value):
                    continue
                for bucket in self.mode_categories.values():
                    if key in bucket:
                        bucket[key] = False
                if key in self.mode_flags:
                    self.mode_flags[key] = False

    @staticmethod
    def _init_mode_profiles(vision_cfg: dict, mode_flags: dict = None) -> Dict[str, Dict[str, bool]]:
        raw_modes = vision_cfg.get("modes", {}) if isinstance(vision_cfg.get("modes"), dict) else {}
        return {
            "balanced": dict(mode_flags) if mode_flags else {},
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

    def get_modes(self) -> Dict[str, bool]:
        return dict(self.mode_flags)

    def get_mode_categories(self) -> Dict[str, Dict[str, bool]]:
        return {
            "local": dict(self.mode_categories.get("local", {})),
            "remote": dict(self.mode_categories.get("remote", {})),
            "onsensor": dict(self.mode_categories.get("onsensor", {})),
        }

    def set_mode_categories(self, updates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
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

        if not self._camera_hardware_available:
            return {
                "ok": False,
                "error": "camera_disabled",
                "processing_mode": self.processing_mode,
            }

        self.processing_mode = "local"
        self._ensure_face_manager()
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

    def set_camera_hardware_available(self, available: bool) -> None:
        self._camera_hardware_available = bool(available)
        if not self._camera_hardware_available:
            self._camera_gave_up = False

    def _needs_local_capture(self) -> bool:
        hybrid = self.hybrid_local_capture and self.processing_mode == "remote"
        return self.processing_mode == "local" or hybrid

    def has_vision_context(self) -> bool:
        try:
            ctx = self.get_latest_visual_context()
            if ctx is not None:
                return True
        except Exception:
            pass
        return bool(self.latest_results)

    def is_local_camera_available(self) -> bool:
        if not self._camera_hardware_available:
            return False
        if not self._needs_local_capture():
            return False
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

    def is_camera_input_available(self) -> bool:
        return self.is_local_camera_available()
