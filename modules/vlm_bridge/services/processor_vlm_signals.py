from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("vlm_bridge.vlm")


class ProcessorVlmSignalsMixin:
    """Scene change, person/hazard detection signals, and budget checks for VLM."""

    mode_categories: Dict[str, Dict[str, bool]]
    mode_flags: Dict[str, bool]
    vision_semantic_budget: Dict[str, Any]
    vision_request_gate: Optional[Any]
    vision_sampler: Optional[Any]
    visual_context_cache: Optional[Any]
    _context_max_age_s: float
    remote_mm_semantic_endpoint: str
    remote_mm_cheap_endpoint: str
    remote_mm_endpoint: str

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

    def _person_signals(self, parsed_results: List[Dict[str, Any]]) -> Tuple[bool, bool]:
        owner_seen = False
        new_person = False
        seen = getattr(self, "_seen_person_names", set())
        current: set = set()
        for r in parsed_results or []:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "").strip()
            if not name or name.lower() == "unknown":
                continue
            current.add(name)
            rel = str(r.get("relationship") or "").lower()
            level = r.get("recognition_level")
            if rel in {"owner", "family"} or (isinstance(level, (int, float)) and level >= 5):
                owner_seen = True
            if name not in seen:
                new_person = True
        self._seen_person_names = (seen | current) if len(seen) < 64 else set(current)
        return owner_seen, new_person

    def _hazard_signal(self, parsed_results: List[Dict[str, Any]]) -> bool:
        alerts_cfg = getattr(self, "config", {}).get("vision", {}).get("alerts", {})
        if not alerts_cfg or not getattr(self, "mode_flags", {}).get("hazards", True):
            return False
        classes = {str(c) for c in alerts_cfg.get("classes", [])}
        dist_thr = float(alerts_cfg.get("distance_threshold_m", 1.0))
        for r in parsed_results or []:
            if not isinstance(r, dict):
                continue
            dist = r.get("distance_m")
            if str(r.get("label") or "") in classes and isinstance(dist, (int, float)) and float(dist) <= dist_thr:
                return True
        return False

    def _vlm_scene_key(self, parsed_results: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        for item in parsed_results or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or "unknown").strip().lower()
            name = str(item.get("name") or "").strip().lower()
            bbox = item.get("bbox") or []
            box_key = ""
            if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                try:
                    box_key = ":".join(str(int(float(x) / 32)) for x in bbox[:4])
                except Exception:
                    box_key = ""
            parts.append(f"{label}:{name}:{box_key}")
        if not parts:
            return "empty"
        return "|".join(sorted(parts)[:24])

    def _vlm_reason_from_signals(
        self,
        *,
        score: float,
        owner_seen: bool,
        new_person: bool,
        hazard: bool,
        sudden_motion: bool,
        is_bored: bool,
    ) -> Tuple[str, str]:
        if hazard:
            return "hazard", "high"
        if new_person:
            return "new_person", "normal"
        if owner_seen:
            return "owner_seen", "normal"
        if sudden_motion:
            return "sudden_motion", "normal"
        sampler = getattr(self, "vision_sampler", None)
        threshold = getattr(sampler, "scene_change_threshold", 0.35)
        if score >= threshold:
            return "scene_change", "normal"
        if is_bored:
            return "boredom", "low"
        return "idle_refresh", "low"

    @staticmethod
    def _init_semantic_budget(config: Dict[str, Any]) -> Dict[str, Any]:
        raw = config.get("vision_semantic_budget", {}) if isinstance(config, dict) else {}
        raw = raw if isinstance(raw, dict) else {}
        default_reasons = {
            "user_question": True,
            "manual_refresh": True,
            "hazard": True,
            "new_person": True,
            "owner_seen": False,
            "scene_change": False,
            "sudden_motion": False,
            "boredom": False,
            "idle_refresh": False,
            "background_refresh": False,
        }
        reasons_raw = raw.get("semantic_reasons", default_reasons)
        reasons: Dict[str, bool] = dict(default_reasons)
        if isinstance(reasons_raw, dict):
            for key, value in reasons_raw.items():
                reasons[str(key)] = bool(value)
        elif isinstance(reasons_raw, (list, tuple, set)):
            reasons = {key: False for key in default_reasons}
            for key in reasons_raw:
                reasons[str(key)] = True
        return {
            "enabled": bool(raw.get("enabled", True)),
            "log_decisions": bool(raw.get("log_decisions", True)),
            "semantic_reasons": reasons,
        }

    def _semantic_budget_allows(self, *, question: str = "", reason: str = "", force: Optional[bool] = None) -> bool:
        if force is not None:
            return bool(force)
        cfg = getattr(self, "vision_semantic_budget", {}) or {}
        if not bool(cfg.get("enabled", True)):
            return False
        if str(question or "").strip():
            return True
        reason_key = str(reason or "background_refresh")
        reasons = cfg.get("semantic_reasons", {}) if isinstance(cfg.get("semantic_reasons", {}), dict) else {}
        return bool(reasons.get(reason_key, False))

    def _visual_context_cache_state(self) -> Tuple[bool, Optional[float]]:
        cache = getattr(self, "visual_context_cache", None)
        if cache is None:
            return False, None
        try:
            age = float(getattr(cache, "age_s", 999999.0))
            latest = cache.get_latest() if hasattr(cache, "get_latest") else None
            return latest is not None and age <= float(getattr(self, "_context_max_age_s", 45.0)), age
        except Exception:
            return False, None

    def get_vision_gate_stats(self) -> Dict[str, Any]:
        gate = getattr(self, "vision_request_gate", None)
        if gate is None:
            return {"available": False}
        try:
            stats = gate.get_stats()
            stats["available"] = True
            return stats
        except Exception as exc:
            return {"available": False, "error": str(exc)}

    def _remote_requested_tasks(self, run_semantic_vlm: bool = False) -> List[str]:
        remote = self.mode_categories.get("remote", {})
        tasks: List[str] = []
        for key in ("objects", "people", "faces", "ocr", "hazards", "semantic_scene", "depth"):
            if key == "semantic_scene" and not run_semantic_vlm:
                continue
            if bool(remote.get(key, False)):
                tasks.append(key)
        return tasks

    def _remote_multimodal_endpoint_for(self, run_semantic_vlm: bool = False) -> str:
        if bool(run_semantic_vlm):
            return getattr(self, "remote_mm_semantic_endpoint", "") or getattr(self, "remote_mm_endpoint", "")
        return getattr(self, "remote_mm_cheap_endpoint", "") or getattr(self, "remote_mm_endpoint", "")
