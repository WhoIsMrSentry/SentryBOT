from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    return max(lo, min(hi, v))


@dataclass
class NeedsSnapshot:
    ok: bool
    timestamp: float
    idle_s: float
    owner_present: bool
    dominant_need: str
    recommended_goal: str
    event: str
    confidence: float
    scores: Dict[str, float]
    reasons: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["scores"] = {k: round(float(v), 1) for k, v in self.scores.items()}
        data["confidence"] = round(float(self.confidence), 2)
        data["idle_s"] = round(float(self.idle_s), 1)
        return data


class CompanionNeedsEngine:
    """Centralized companion needs model.

    This is intentionally semantic, not hardware-specific. It converts runtime
    context into need intensities and a recommended high-level goal. Hardware
    output is handled later by the expression/output bridge.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "boredom_threshold_s": 35.0,
        "alone_threshold_s": 120.0,
        "low_energy_threshold": 25.0,
        "event_cooldown_s": 18.0,
        "owner_recent_timeout_s": 35.0,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self.enabled = bool(self.cfg.get("enabled", True))
        self._last_snapshot: Optional[NeedsSnapshot] = None
        self._last_event_ts: float = 0.0
        self._last_event_name: str = ""
        self._last_interaction_source: str = ""

    def observe_interaction(self, source: str = "") -> None:
        self._last_interaction_source = str(source or "interaction").strip().lower()

    def tick(
        self,
        *,
        now: Optional[float] = None,
        last_interaction_ts: Optional[float] = None,
        mood_state: Optional[Dict[str, Any]] = None,
        needs_state: Optional[Dict[str, Any]] = None,
        owner_present: bool = False,
        owner_last_seen_ts: Optional[float] = None,
        is_sleeping: bool = False,
        speech_busy: bool = False,
        scene: Optional[Dict[str, Any]] = None,
        pc_test: bool = False,
    ) -> Dict[str, Any]:
        now_ts = float(now if now is not None else time.time())
        last_ts = float(last_interaction_ts or now_ts)
        idle_s = max(0.0, now_ts - last_ts)
        mood = mood_state if isinstance(mood_state, dict) else {}
        needs = needs_state if isinstance(needs_state, dict) else {}
        scene_map = scene if isinstance(scene, dict) else {}
        audio_map = scene_map.get("audio_context") if isinstance(scene_map.get("audio_context"), dict) else {}
        audio_wakeword = bool(audio_map.get("wakeword"))
        audio_speech = bool(audio_map.get("speech"))
        audio_sound = bool(audio_map.get("sound"))
        audio_silence = bool(audio_map.get("silence"))
        audio_loud = bool(audio_map.get("loud"))
        scene_novelty = bool(scene_map.get("new_object") or scene_map.get("novelty") or scene_map.get("unknown_object"))
        scene_no_person = bool(scene_map.get("no_person"))
        scene_stable = bool(scene_map.get("scene_stable") or scene_map.get("stable"))
        scene_person_seen = bool(scene_map.get("person_seen") or scene_map.get("owner_present"))

        boredom_threshold = max(5.0, float(self.cfg.get("boredom_threshold_s", 35.0) or 35.0))
        alone_threshold = max(boredom_threshold, float(self.cfg.get("alone_threshold_s", 120.0) or 120.0))
        low_energy = max(1.0, float(self.cfg.get("low_energy_threshold", 25.0) or 25.0))

        energy = _clamp(mood.get("energy", 100.0))
        mood_curiosity = _clamp(mood.get("curiosity", 50.0))
        mood_fear = _clamp(mood.get("fear", 0.0))
        existing_social = _clamp(needs.get("social", 50.0))
        existing_stimulation = _clamp(needs.get("stimulation", 40.0))
        existing_rest = _clamp(needs.get("rest", 80.0))

        boredom = _clamp((idle_s / boredom_threshold) * 100.0)
        social_need = _clamp((idle_s / alone_threshold) * 100.0)
        if owner_present:
            social_need = max(0.0, social_need - 45.0)
        social_need = _clamp((social_need * 0.65) + (existing_social * 0.35))

        curiosity = _clamp((mood_curiosity * 0.45) + (existing_stimulation * 0.35) + (boredom * 0.20))
        rest_need = _clamp((100.0 - energy) * 0.75 + max(0.0, 55.0 - existing_rest) * 0.25)
        safety = _clamp(100.0 - mood_fear)
        if scene_map.get("hazards"):
            safety = min(safety, 35.0)
        if pc_test:
            safety = max(safety, 85.0)

        if scene_person_seen:
            owner_present = True
        if audio_wakeword or audio_speech:
            owner_present = True
        owner_proximity = 100.0 if owner_present else 0.0
        if not owner_present and owner_last_seen_ts:
            timeout = max(1.0, float(self.cfg.get("owner_recent_timeout_s", 35.0) or 35.0))
            owner_proximity = _clamp(100.0 - ((now_ts - float(owner_last_seen_ts)) / timeout) * 100.0)

        if audio_wakeword or audio_speech:
            social_need = max(social_need, 82.0)
            curiosity = max(curiosity, 62.0)
        if audio_sound:
            curiosity = max(curiosity, 72.0)
        if audio_silence:
            boredom = max(boredom, min(68.0, boredom + 12.0))
        if audio_loud:
            safety = min(safety, 45.0)
            curiosity = max(curiosity, 68.0)

        exploration = _clamp((curiosity * 0.55) + (boredom * 0.30) + (energy * 0.15))
        if energy < low_energy:
            exploration *= 0.45
        if safety < 50.0:
            exploration *= 0.35
        if audio_sound and safety >= 50.0:
            exploration = max(exploration, 66.0)
        if scene_novelty:
            curiosity = max(curiosity, 82.0)
            exploration = max(exploration, 72.0)
        if scene_no_person and idle_s >= (boredom_threshold * 0.45):
            exploration = max(exploration, 64.0)
            boredom = max(boredom, min(70.0, boredom + 8.0))
        if scene_stable and not scene_novelty and not scene_map.get("hazards") and idle_s < boredom_threshold:
            curiosity = min(curiosity, 52.0)
            exploration = min(exploration, 48.0)

        scores = {
            "social": social_need,
            "curiosity": curiosity,
            "boredom": boredom,
            "energy": energy,
            "rest": rest_need,
            "safety": safety,
            "owner_proximity": owner_proximity,
            "exploration": exploration,
        }
        dominant, goal = self._choose_goal(scores, is_sleeping=is_sleeping, speech_busy=speech_busy)
        event = self._maybe_event(dominant, now_ts)
        confidence = self._confidence(scores, dominant)

        snap = NeedsSnapshot(
            ok=True,
            timestamp=now_ts,
            idle_s=idle_s,
            owner_present=bool(owner_present),
            dominant_need=dominant,
            recommended_goal=goal,
            event=event,
            confidence=confidence,
            scores=scores,
            reasons={
                "pc_test": bool(pc_test),
                "sleeping": bool(is_sleeping),
                "speech_busy": bool(speech_busy),
                "last_interaction_source": self._last_interaction_source,
                "scene_hazards": bool(scene_map.get("hazards")),
                "audio_context": {"wakeword": audio_wakeword, "speech": audio_speech, "sound": audio_sound, "silence": audio_silence, "loud": audio_loud},
                "vision_context": {"new_object": scene_novelty, "no_person": scene_no_person, "scene_stable": scene_stable, "person_seen": scene_person_seen},
            },
        )
        self._last_snapshot = snap
        return snap.to_dict()

    def snapshot(self) -> Dict[str, Any]:
        if self._last_snapshot is None:
            return {
                "ok": True,
                "available": False,
                "reason": "no_snapshot_yet",
                "enabled": self.enabled,
            }
        data = self._last_snapshot.to_dict()
        data["available"] = True
        data["enabled"] = self.enabled
        return data

    def _choose_goal(self, scores: Dict[str, float], *, is_sleeping: bool, speech_busy: bool) -> tuple[str, str]:
        if is_sleeping:
            return "rest", "stay_asleep"
        if speech_busy:
            return "conversation", "listen_and_respond"
        if scores.get("safety", 100.0) < 55.0:
            return "safety", "pause_and_observe"
        if scores.get("rest", 0.0) >= 72.0:
            return "rest", "rest_quietly"
        if scores.get("social", 0.0) >= 70.0:
            return "social", "seek_owner_or_invite_interaction"
        if scores.get("exploration", 0.0) >= 68.0:
            return "exploration", "look_around_and_learn"
        if scores.get("boredom", 0.0) >= 60.0:
            return "boredom", "choose_idle_activity"
        if scores.get("curiosity", 0.0) >= 65.0:
            return "curiosity", "inspect_environment"
        return "balance", "calm_idle"

    def _maybe_event(self, dominant: str, now_ts: float) -> str:
        if not self.enabled:
            return ""
        cooldown = max(1.0, float(self.cfg.get("event_cooldown_s", 18.0) or 18.0))
        event = f"needs.{dominant}"
        if event == self._last_event_name and (now_ts - self._last_event_ts) < cooldown:
            return ""
        if (now_ts - self._last_event_ts) < max(2.0, cooldown / 3.0):
            return ""
        self._last_event_name = event
        self._last_event_ts = now_ts
        return event

    @staticmethod
    def _confidence(scores: Dict[str, float], dominant: str) -> float:
        if dominant in {"balance", "conversation"}:
            return 0.55
        val = float(scores.get(dominant, 50.0) or 50.0)
        if dominant == "safety":
            val = 100.0 - val
        return _clamp(0.35 + (val / 100.0) * 0.55, 0.35, 0.95)