from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

from .state_events import ExpressionStateEventsMixin, _DEFAULT_MAPPINGS

_ALLOWED_EMOTIONS = {
    "neutral", "curious", "happy", "sleepy", "alert", "sad", "thinking", "listening", "speaking"
}
_ALLOWED_AROUSAL = {"low", "medium", "high"}
_ALLOWED_ATTENTION = {"idle", "user", "sound", "object", "sleep", "internal", "camera"}
_ALLOWED_ENERGY = {"low", "normal", "high"}


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


class SemanticExpressionEngine(ExpressionStateEventsMixin):
    """Single semantic expression state for LED/OLED/pose/speech tone arbitration."""

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
