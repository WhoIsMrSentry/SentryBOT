from __future__ import annotations

import time
from typing import Any, Dict, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp01(value: Any, default: float = 0.0) -> float:
    return max(0.0, min(1.0, _as_float(value, default)))


class LivingNeedsEngine:
    """Utility-style pet needs model.

    Values are normalized 0..1 and intentionally semantic. Low-level servo,
    motor and LED details stay inside deterministic capability/safety layers.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "idle_boredom_s": 90.0,
        "alone_social_s": 180.0,
        "curiosity_decay_s": 150.0,
        "rest_energy_threshold": 0.28,
        "sound_attention_hold_s": 18.0,
        "person_attention_hold_s": 45.0,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self._last: Dict[str, Any] = {"ok": True, "available": False, "reason": "never_ticked"}

    def tick(
        self,
        *,
        now: Optional[float] = None,
        state: Optional[Dict[str, Any]] = None,
        mood: Any = None,
        vision: Optional[Dict[str, Any]] = None,
        audio: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        st = state if isinstance(state, dict) else {}
        vision_map = vision if isinstance(vision, dict) else {}
        audio_map = audio if isinstance(audio, dict) else {}

        last_interaction = _as_float(st.get("last_interaction"), ts)
        idle_s = max(0.0, ts - last_interaction)
        owner_last_seen = _as_float(st.get("owner_last_seen"), 0.0)
        owner_absent_s = max(0.0, ts - owner_last_seen) if owner_last_seen > 0 else idle_s
        owner_present = bool(owner_last_seen > 0 and owner_absent_s <= float(self.cfg.get("person_attention_hold_s", 45.0)))

        energy_raw = 100.0
        try:
            if hasattr(mood, "get"):
                energy_raw = _as_float(mood.get("energy", 100.0), 100.0)
            elif isinstance(mood, dict):
                energy_raw = _as_float(mood.get("energy"), 100.0)
        except Exception:
            energy_raw = 100.0
        energy = max(0.0, min(1.0, energy_raw / 100.0 if energy_raw > 1.0 else energy_raw))

        # Organik Homeostaz (Pil seviyesi ve Termal Yorgunluk Etkisi)
        battery_pct = _as_float(st.get("battery_pct") or st.get("battery_level") or (st.get("battery") or {}).get("pct"), 100.0)
        cpu_temp = _as_float(st.get("cpu_temp") or st.get("temperature") or (st.get("telemetry") or {}).get("cpu_temp"), 45.0)

        # Düşük batarya (<30%): Enerji doğrudan düşer, dinlenme ihtiyacı (rest) tetiklenir
        if battery_pct < 30.0:
            energy *= max(0.1, battery_pct / 30.0)

        # Yüksek CPU sıcaklığı (>70°C): Aşırı ısınmada halsizlik/termal yorgunluk hissi
        if cpu_temp > 70.0:
            thermal_penalty = min(0.5, (cpu_temp - 70.0) / 20.0)
            energy = max(0.1, energy - thermal_penalty)

        people_count = self._count_people(vision_map)
        objects_count = self._count_objects(vision_map)
        hazards_count = self._count_hazards(vision_map)
        last_sound_ts = _as_float(audio_map.get("timestamp") or audio_map.get("last_sound_ts"), 0.0)
        sound_recent = last_sound_ts > 0 and (ts - last_sound_ts) <= float(self.cfg.get("sound_attention_hold_s", 18.0))
        speech_busy = bool(st.get("speech_busy") or audio_map.get("speech_busy"))

        boredom = _clamp01(idle_s / max(1.0, float(self.cfg.get("idle_boredom_s", 90.0))))
        social = _clamp01(owner_absent_s / max(1.0, float(self.cfg.get("alone_social_s", 180.0))))
        if owner_present or people_count > 0:
            social *= 0.25
            boredom *= 0.55
        curiosity = 0.25 + min(0.55, objects_count * 0.09)
        if sound_recent:
            curiosity = max(curiosity, 0.72)
        if people_count == 0 and idle_s > 30:
            curiosity = max(curiosity, min(0.85, idle_s / max(1.0, float(self.cfg.get("curiosity_decay_s", 150.0)))))
        rest = _clamp01((float(self.cfg.get("rest_energy_threshold", 0.28)) - energy) / 0.28)
        if battery_pct < 30.0:
            rest = max(rest, _clamp01((30.0 - battery_pct) / 30.0))
        if cpu_temp > 70.0:
            rest = max(rest, _clamp01((cpu_temp - 70.0) / 20.0))
        safety = _clamp01(hazards_count / 2.0)
        attachment = 1.0 - min(1.0, owner_absent_s / 900.0) if owner_last_seen > 0 else 0.35

        scores = {
            "social": round(social, 3),
            "curiosity": round(_clamp01(curiosity), 3),
            "boredom": round(boredom, 3),
            "rest": round(rest, 3),
            "safety": round(safety, 3),
            "attachment": round(_clamp01(attachment), 3),
            "energy": round(energy, 3),
        }
        dominant = max((k for k in scores if k != "energy"), key=lambda key: scores[key])
        recommended = self._goal_for(dominant, people_count=people_count, sound_recent=sound_recent)
        out = {
            "ok": True,
            "available": bool(self.cfg.get("enabled", True)),
            "timestamp": ts,
            "idle_s": round(idle_s, 2),
            "owner_absent_s": round(owner_absent_s, 2),
            "owner_present": bool(owner_present),
            "people_count": int(people_count),
            "objects_count": int(objects_count),
            "hazards_count": int(hazards_count),
            "sound_recent": bool(sound_recent),
            "speech_busy": bool(speech_busy),
            "scores": scores,
            "dominant_need": dominant,
            "recommended_goal": recommended,
            "confidence": round(max(v for k, v in scores.items() if k != "energy"), 3),
            "semantic_state": {
                "emotion": self._emotion_for(dominant),
                "attention": "sound" if sound_recent else ("person" if people_count else "environment"),
                "energy": scores["energy"],
                "arousal": max(scores["curiosity"], scores["safety"], 0.2),
            },
        }
        self._last = dict(out)
        return out

    def status(self) -> Dict[str, Any]:
        return {"ok": True, "enabled": bool(self.cfg.get("enabled", True)), "config": dict(self.cfg), "last": dict(self._last)}

    @staticmethod
    def _count_people(vision: Dict[str, Any]) -> int:
        tracks = vision.get("tracks") if isinstance(vision.get("tracks"), list) else []
        people = [x for x in tracks if isinstance(x, dict) and str(x.get("label") or "").lower() == "person"]
        if people:
            return len(people)
        people_ctx = vision.get("people") if isinstance(vision.get("people"), list) else []
        return len(people_ctx)

    @staticmethod
    def _count_objects(vision: Dict[str, Any]) -> int:
        tracks = vision.get("tracks") if isinstance(vision.get("tracks"), list) else []
        if tracks:
            return len([x for x in tracks if isinstance(x, dict) and str(x.get("label") or "").lower() != "person"])
        objects = vision.get("objects") if isinstance(vision.get("objects"), list) else []
        return len(objects)

    @staticmethod
    def _count_hazards(vision: Dict[str, Any]) -> int:
        hazards = vision.get("hazards") if isinstance(vision.get("hazards"), list) else []
        return len(hazards)

    @staticmethod
    def _goal_for(dominant: str, *, people_count: int, sound_recent: bool) -> str:
        if dominant == "safety":
            return "pause_and_observe"
        if dominant == "rest":
            return "rest_in_safe_place"
        if sound_recent:
            return "inspect_sound_source"
        if dominant == "boredom" and people_count == 0:
            return "look_for_company_or_rest"
        if dominant == "curiosity":
            return "inspect_environment"
        if dominant == "social":
            return "seek_owner_or_person"
        return "calm_idle"

    @staticmethod
    def _emotion_for(dominant: str) -> str:
        return {
            "safety": "worried",
            "rest": "tired",
            "boredom": "bored",
            "curiosity": "curiosity",
            "social": "curiosity",
            "attachment": "calm",
        }.get(str(dominant), "neutral")


__all__ = ["LivingNeedsEngine"]
