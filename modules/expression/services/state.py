from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

_ALLOWED_EMOTIONS = {
    "neutral", "curious", "happy", "sleepy", "alert", "sad", "thinking", "listening", "speaking"
}
_ALLOWED_AROUSAL = {"low", "medium", "high"}
_ALLOWED_ATTENTION = {"idle", "user", "sound", "object", "sleep", "internal", "camera"}
_ALLOWED_ENERGY = {"low", "normal", "high"}

_DEFAULT_MAPPINGS = {
    "colors": {
        "neutral": "#4060ff",
        "curious": "#00bcd4",
        "happy": "#00ff88",
        "sleepy": "#203050",
        "alert": "#ffb000",
        "sad": "#2050ff",
        "thinking": "#7a5cff",
        "listening": "#00aaff",
        "speaking": "#00ffcc",
    },
    "oled_moods": {
        "neutral": "neutral",
        "curious": "curious",
        "happy": "happy",
        "sleepy": "sleepy",
        "alert": "alert",
        "sad": "sad",
        "thinking": "thinking",
    },
    "led_modes": {
        "idle": "breathe",
        "user": "listen",
        "sound": "pulse",
        "object": "eye",
        "sleep": "off",
        "internal": "thinking",
    },
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "curiosity": "curious",
        "curiousity": "curious",
        "joy": "happy",
        "tired": "sleepy",
        "bored": "curious",
        "wake": "alert",
        "listen": "listening",
        "talking": "speaking",
        "asleep": "sleepy",
    }
    text = aliases.get(text, text)
    return text if text in allowed else default
def _float01(value: Any, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, v))


@dataclass
class ExpressionState:
    emotion: str = "neutral"
    arousal: str = "low"
    attention: str = "idle"
    energy: str = "normal"
    speaking: bool = False
    listening: bool = False
    confidence: float = 0.5
    source: str = "system"
    reason: str = "boot"
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        if not out.get("updated_at"):
            out["updated_at"] = _utc_iso()
        return out


class SemanticExpressionEngine:
    """Single semantic expression state for LED/OLED/pose/speech tone arbitration.

    This first refactor step does not seize hardware outputs directly. It creates a
    truthful semantic state and a deterministic target map that later hardware
    bridges can consume without fighting each other.
    """

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = cfg or {}
        state_cfg = self.cfg.get("state", {}) if isinstance(self.cfg.get("state", {}), dict) else {}
        self._lock = threading.RLock()
        self._max_history = int(state_cfg.get("max_history", 120))
        self._state = ExpressionState(
            emotion=_choice(state_cfg.get("default_emotion"), _ALLOWED_EMOTIONS, "neutral"),
            arousal=_choice(state_cfg.get("default_arousal"), _ALLOWED_AROUSAL, "low"),
            attention=_choice(state_cfg.get("default_attention"), _ALLOWED_ATTENTION, "idle"),
            energy=_choice(state_cfg.get("default_energy"), _ALLOWED_ENERGY, "normal"),
            updated_at=_utc_iso(),
        )
        self._history: List[Dict[str, Any]] = []
        self._event_counts: Dict[str, int] = {}

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            state = self._state.to_dict()
            return {
                "ok": True,
                "state": state,
                "targets": self._derive_targets(state),
                "event_counts": dict(self._event_counts),
                "history_size": len(self._history),
            }

    def history(self, limit: int = 30) -> Dict[str, Any]:
        with self._lock:
            n = max(1, min(int(limit), self._max_history))
            return {"ok": True, "history": list(self._history[-n:])}

    def apply(self, payload: Dict[str, Any], *, source: str = "api", reason: str = "manual") -> Dict[str, Any]:
        if not isinstance(payload, dict):
            payload = {}
        with self._lock:
            prev = self._state.to_dict()
            next_state = ExpressionState(**prev)
            if "emotion" in payload:
                next_state.emotion = _choice(payload.get("emotion"), _ALLOWED_EMOTIONS, next_state.emotion)
            if "arousal" in payload:
                next_state.arousal = _choice(payload.get("arousal"), _ALLOWED_AROUSAL, next_state.arousal)
            if "attention" in payload:
                next_state.attention = _choice(payload.get("attention"), _ALLOWED_ATTENTION, next_state.attention)
            if "energy" in payload:
                next_state.energy = _choice(payload.get("energy"), _ALLOWED_ENERGY, next_state.energy)
            if "speaking" in payload:
                next_state.speaking = bool(payload.get("speaking"))
            if "listening" in payload:
                next_state.listening = bool(payload.get("listening"))
            if "confidence" in payload:
                next_state.confidence = _float01(payload.get("confidence"), next_state.confidence)
            next_state.source = str(payload.get("source") or source or "api")[:80]
            next_state.reason = str(payload.get("reason") or reason or "manual")[:160]
            next_state.updated_at = _utc_iso()
            self._state = next_state
            record = {"at": next_state.updated_at, "prev": prev, "next": next_state.to_dict()}
            self._history.append(record)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            return self.get_state()

    def event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        evt = str(event_type or "").strip().lower()
        data = data if isinstance(data, dict) else {}
        with self._lock:
            if evt:
                self._event_counts[evt] = int(self._event_counts.get(evt, 0)) + 1
        patch = self._patch_for_event(evt, data)
        if patch:
            patch.setdefault("source", "event")
            patch.setdefault("reason", evt or "event")
            return self.apply(patch, source="event", reason=evt or "event")
        return self.get_state()

    def on_interaction_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.event(event_type, data)

    def status(self) -> Dict[str, Any]:
        payload = self.get_state()
        return {
            "ok": True,
            "emotion": payload["state"]["emotion"],
            "arousal": payload["state"]["arousal"],
            "attention": payload["state"]["attention"],
            "targets": payload["targets"],
        }

    def _patch_for_event(self, evt: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if not evt:
            return {}
        evt = str(evt or "").strip().lower()
        data = data if isinstance(data, dict) else {}

        if evt.startswith("needs."):
            need = evt.split(".", 1)[1].strip().lower()
            scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
            goal = str(data.get("recommended_goal") or data.get("goal") or "").strip().lower()
            confidence = data.get("confidence", 0.75)
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.75
            confidence = max(0.35, min(0.95, confidence))

            if need in {"exploration", "curiosity"}:
                return {
                    "emotion": "curious",
                    "arousal": "medium" if need == "exploration" else "low",
                    "attention": "camera" if "look" in goal or "learn" in goal or need == "exploration" else "internal",
                    "energy": "normal",
                    "confidence": confidence,
                    "reason": "needs." + need,
                }
            if need == "boredom":
                return {
                    "emotion": "curious",
                    "arousal": "medium",
                    "attention": "internal",
                    "energy": "normal",
                    "confidence": confidence,
                    "reason": "boredom",
                }
            if need == "social":
                return {
                    "emotion": "happy",
                    "arousal": "medium",
                    "attention": "user",
                    "energy": "normal",
                    "confidence": confidence,
                    "reason": "needs.social",
                }
            if need == "rest":
                return {
                    "emotion": "sleepy",
                    "arousal": "low",
                    "attention": "sleep",
                    "energy": "low",
                    "speaking": False,
                    "listening": False,
                    "confidence": confidence,
                    "reason": "needs.rest",
                }
            if need == "safety":
                return {
                    "emotion": "alert",
                    "arousal": "high",
                    "attention": "internal",
                    "energy": "high",
                    "confidence": confidence,
                    "reason": "needs.safety",
                }
            if need in {"owner_proximity", "owner"}:
                return {
                    "emotion": "curious",
                    "arousal": "medium",
                    "attention": "user",
                    "energy": "normal",
                    "confidence": confidence,
                    "reason": "needs.owner_proximity",
                }
            if need == "balance":
                return {
                    "emotion": "neutral",
                    "arousal": "low",
                    "attention": "idle",
                    "energy": "normal",
                    "confidence": max(0.45, min(0.7, confidence)),
                    "reason": "needs.balance",
                }
            return {
                "emotion": "thinking",
                "arousal": "low",
                "attention": "internal",
                "confidence": max(0.4, min(0.75, confidence)),
                "reason": "needs." + need,
            }

        if evt in {"wakeword.detected", "wakeword.wake", "speech.wake"}:
            return {"emotion": "listening", "arousal": "high", "attention": "user", "energy": "high", "listening": True, "confidence": 0.95}
        if evt in {"speech.listen.start", "speech.listening", "speech.started"}:
            return {"emotion": "listening", "arousal": "medium", "attention": "user", "listening": True, "confidence": 0.85}
        if evt in {"speech.listen.stop", "speech.final", "speech.transcribed"}:
            return {"emotion": "thinking", "arousal": "medium", "attention": "internal", "listening": False, "confidence": 0.85}
        if evt in {"speak.started", "tts.started", "speech.speaking"}:
            return {"emotion": "speaking", "arousal": "medium", "attention": "user", "speaking": True, "listening": False, "confidence": 0.9}
        if evt in {"speak.finished", "tts.finished", "speech.done"}:
            return {"emotion": "neutral", "arousal": "low", "attention": "idle", "speaking": False, "confidence": 0.75}

        if evt in {"sound.detected", "audio.sound", "audio.clap", "audio.direction"}:
            return {"emotion": "alert", "arousal": "high", "attention": "sound", "energy": "high", "confidence": 0.9}
        if evt in {"vision.person", "vision.owner", "person.detected", "owner.seen", "owner.detected"}:
            return {"emotion": "curious", "arousal": "medium", "attention": "user", "energy": "normal", "confidence": 0.85}
        if evt in {"vision.focus", "vision.object", "object.detected"}:
            return {"emotion": "curious", "arousal": "medium", "attention": "object", "confidence": 0.8}
        if evt in {"owner.scan", "vision.scan", "camera.scan"}:
            return {"emotion": "curious", "arousal": "low", "attention": "camera", "energy": "normal", "confidence": 0.65}

        if evt in {"agent.thinking", "llm.thinking", "brain.thinking"}:
            return {"emotion": "thinking", "arousal": "medium", "attention": "internal", "confidence": 0.85}
        if evt in {"llm.unavailable", "llm.chat_unavailable", "ollama.unavailable", "ai.unavailable"}:
            return {"emotion": "thinking", "arousal": "low", "attention": "internal", "confidence": 0.25, "reason": "llm_unavailable"}
        if evt == "error":
            src = str(data.get("source") or "").lower()
            reason = str(data.get("reason") or "").lower()
            if "ollama" in src or "llm" in src or "chat" in reason:
                return {"emotion": "thinking", "arousal": "low", "attention": "internal", "confidence": 0.25, "reason": "llm_unavailable"}
            return {"emotion": "alert", "arousal": "high", "attention": "internal", "confidence": 0.4}

        if evt in {"autonomy.sleep", "sleep.start", "idle.sleep"}:
            return {"emotion": "sleepy", "arousal": "low", "attention": "sleep", "energy": "low", "speaking": False, "listening": False, "confidence": 0.9}
        if evt in {"autonomy.wake", "sleep.stop", "wake.start"}:
            return {"emotion": "alert", "arousal": "medium", "attention": "idle", "energy": "normal", "confidence": 0.8}
        if evt in {"autonomy.idle", "idle", "idle.tick"}:
            return {"emotion": "neutral", "arousal": "low", "attention": "idle", "energy": "normal", "confidence": 0.6}

        if evt in {"autonomy.look_around", "idle.look_around", "gesture:look_around"}:
            return {"emotion": "curious", "arousal": "low", "attention": "camera", "energy": "normal", "confidence": 0.8}
        if evt in {"autonomy.blink", "idle.blink"}:
            return {"emotion": "neutral", "arousal": "low", "attention": "idle", "energy": "normal", "confidence": 0.65}
        if evt in {"autonomy.bored", "boredom.detected", "robot.bored"}:
            return {"emotion": "curious", "arousal": "medium", "attention": "internal", "energy": "normal", "confidence": 0.85, "reason": "boredom"}
        if evt in {"autonomy.stretch", "idle.stretch"}:
            return {"emotion": "neutral", "arousal": "medium", "attention": "idle", "energy": "high", "confidence": 0.75}
        if evt in {"autonomy.monologue", "idle.monologue"}:
            return {"emotion": "thinking", "arousal": "medium", "attention": "internal", "energy": "normal", "confidence": 0.75}
        if evt in {"autonomy.excited"}:
            return {"emotion": "happy", "arousal": "high", "attention": "user", "energy": "high", "confidence": 0.85}
        if evt in {"autonomy.offline"}:
            return {"emotion": "thinking", "arousal": "low", "attention": "internal", "confidence": 0.35}

        if evt in {"companion.proactive", "companion.event", "companion.curiosity", "companion.ritual"}:
            emotion = data.get("emotion") or data.get("mood") or "curious"
            text = str(data.get("text") or "").strip()
            patch = {"emotion": emotion, "arousal": "medium", "attention": "internal", "energy": "normal", "confidence": 0.85}
            if text:
                patch["reason"] = "companion:" + text[:120]
            return patch
        if evt in {"idle.behavior", "idle.behavior.selected", "autonomy.idle_behavior"}:
            behavior = str(data.get("behavior") or data.get("name") or "").lower()
            if "sleep" in behavior or "sigh" in behavior:
                return {"emotion": "sleepy", "arousal": "low", "attention": "idle", "energy": "low", "confidence": 0.75}
            if "look" in behavior:
                return {"emotion": "curious", "arousal": "low", "attention": "camera", "energy": "normal", "confidence": 0.75}
            if "blink" in behavior:
                return {"emotion": "neutral", "arousal": "low", "attention": "idle", "energy": "normal", "confidence": 0.65}
            if "stretch" in behavior:
                return {"emotion": "neutral", "arousal": "medium", "attention": "idle", "energy": "high", "confidence": 0.75}
            if "monologue" in behavior:
                return {"emotion": "thinking", "arousal": "medium", "attention": "internal", "energy": "normal", "confidence": 0.75}
            return {"emotion": "neutral", "arousal": "low", "attention": "idle", "energy": "normal", "confidence": 0.55}

        if evt.startswith("scene.emotion_"):
            raw = evt.split("scene.emotion_", 1)[1]
            emotion = raw.split(".", 1)[0]
            if raw.endswith(".end"):
                return {"emotion": "neutral", "arousal": "low", "attention": "idle", "confidence": 0.55}
            return {"emotion": emotion, "arousal": "medium", "attention": "camera", "confidence": 0.7}
        if evt.startswith("emotion:"):
            return {"emotion": evt.split(":", 1)[1], "arousal": data.get("arousal", "medium"), "confidence": data.get("confidence", 0.75)}
        if evt.startswith("gesture:"):
            gesture = evt.split(":", 1)[1]
            if gesture in {"look", "look_around", "scan"}:
                return {"emotion": "curious", "arousal": "low", "attention": "camera", "confidence": 0.65}
            if gesture in {"happy", "excited"}:
                return {"emotion": "happy", "arousal": "high", "attention": "user", "confidence": 0.75}
        return {}

    def _derive_targets(self, state: Dict[str, Any]) -> Dict[str, Any]:
        configured = self.cfg.get("mappings", {}) if isinstance(self.cfg.get("mappings", {}), dict) else {}
        mappings = dict(_DEFAULT_MAPPINGS)
        for key, value in configured.items():
            if isinstance(value, dict) and isinstance(mappings.get(key), dict):
                merged = dict(mappings[key])
                merged.update(value)
                mappings[key] = merged
            else:
                mappings[key] = value
        colors = mappings.get("colors", {}) if isinstance(mappings.get("colors", {}), dict) else {}
        oled = mappings.get("oled_moods", {}) if isinstance(mappings.get("oled_moods", {}), dict) else {}
        led_modes = mappings.get("led_modes", {}) if isinstance(mappings.get("led_modes", {}), dict) else {}
        emotion = str(state.get("emotion") or "neutral")
        attention = str(state.get("attention") or "idle")
        color = str(colors.get(emotion) or colors.get("neutral") or "#4060ff")
        led_mode = str(led_modes.get(attention) or led_modes.get("idle") or "breathe")
        if state.get("speaking"):
            led_mode = "listen_vu"
            color = str(colors.get("speaking") or color)
        elif state.get("listening"):
            led_mode = "listen"
            color = str(colors.get("listening") or color)
        return {
            "led": {"mode": led_mode, "color": color, "emotion": emotion},
            "oled": {"mood": str(oled.get(emotion) or emotion), "attention": attention},
            "pose": {"ear_gesture": self._ear_gesture(state), "energy": state.get("energy")},
            "speech": {"tone": emotion, "arousal": state.get("arousal")},
        }

    @staticmethod
    def _ear_gesture(state: Dict[str, Any]) -> str:
        attention = str(state.get("attention") or "idle")
        emotion = str(state.get("emotion") or "neutral")
        if attention == "sound":
            return "sound"
        if emotion in {"sleepy"} or attention == "sleep":
            return "sleep"
        if emotion in {"curious", "listening", "thinking"}:
            return "attend"
        if emotion in {"happy", "speaking"}:
            return "happy"
        if emotion == "alert":
            return "alert"
        return "idle"
