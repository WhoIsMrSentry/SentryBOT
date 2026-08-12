
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled", "detected", "present", "active"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


class AudioEventNeedsBridge:
    """Semantic audio context bridge for companion needs.

    This layer does not do speech recognition. It accepts already-detected audio
    events such as wakeword, speech, sound, silence, or loud noise, and exposes a
    short-lived semantic context to the needs engine.
    """

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "ttl_s": 30.0,
        "owner_audio_timeout_s": 45.0,
        "history_limit": 20,
        "wakeword_social": 96.0,
        "speech_social": 86.0,
        "sound_curiosity": 76.0,
        "silence_boredom": 58.0,
        "loud_fear": 60.0,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self._latest: Dict[str, Any] = {
            "ok": True,
            "available": False,
            "reason": "no_audio_event_yet",
            "timestamp": 0.0,
        }
        self._owner_last_heard_ts: float = 0.0
        self._history: List[Dict[str, Any]] = []

    def observe(self, payload: Optional[Dict[str, Any]], *, source: str = "manual", now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        data = _as_dict(payload)
        event_type = str(data.get("type") or data.get("event") or data.get("kind") or "").strip().lower()
        transcript = str(data.get("transcript") or data.get("text") or "").strip()
        confidence = max(0.0, min(1.0, _as_float(data.get("confidence"), 0.7)))
        wakeword = _as_bool(data.get("wakeword"), False) or event_type in {"wakeword", "wakeword.detected", "owner.call"}
        speech = _as_bool(data.get("speech"), False) or event_type in {"speech", "speech.detected", "voice"} or bool(transcript)
        sound = _as_bool(data.get("sound"), False) or event_type in {"sound", "sound.detected", "noise"}
        silence = _as_bool(data.get("silence"), False) or event_type in {"silence", "silence.long", "quiet"}
        loud = _as_bool(data.get("loud"), False) or _as_bool(data.get("loud_noise"), False) or event_type in {"loud", "loud_noise", "alarm", "bang"}
        owner_present = _as_bool(data.get("owner_present"), False) or wakeword or speech
        speech_busy = _as_bool(data.get("speech_busy"), False)
        
        # Extract sound direction (azimuth in degrees, e.g. -90 to +90)
        sound_angle = _as_float(data.get("sound_angle", data.get("azimuth", 0.0)), 0.0)
        # Convert azimuth to servo pan (90 is center)
        suggested_pan = max(0, min(180, int(90 + sound_angle))) if sound_angle != 0.0 else None

        if wakeword or speech or owner_present:
            self._owner_last_heard_ts = ts
        result = {
            "ok": True,
            "available": True,
            "timestamp": ts,
            "source": str(source or data.get("source") or "manual"),
            "event_type": event_type or self._derive_event(wakeword, speech, sound, silence, loud),
            "wakeword": bool(wakeword),
            "speech": bool(speech),
            "sound": bool(sound),
            "silence": bool(silence),
            "loud": bool(loud),
            "owner_present": bool(owner_present),
            "speech_busy": bool(speech_busy),
            "sound_angle": sound_angle,
            "suggested_pan": suggested_pan,
            "transcript": transcript,
            "confidence": round(confidence, 2),
            "reason": self._reason_for(wakeword=wakeword, speech=speech, sound=sound, silence=silence, loud=loud),
        }
        self._latest = result
        self._push_history(result)
        return self.status(now=ts)

    def status(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        latest = dict(self._latest)
        age = max(0.0, ts - _as_float(latest.get("timestamp"), 0.0)) if latest.get("available") else 0.0
        ttl = max(1.0, _as_float(self.cfg.get("ttl_s"), 30.0))
        latest["enabled"] = _as_bool(self.cfg.get("enabled"), True)
        latest["age_s"] = round(age, 1)
        latest["fresh"] = bool(latest.get("available") and age <= ttl)
        latest["owner_last_heard_ts"] = self._owner_last_heard_ts
        latest["history"] = list(self._history[-10:])
        return latest

    def context(self, *, now: Optional[float] = None) -> Dict[str, Any]:
        ts = float(now if now is not None else time.time())
        if not _as_bool(self.cfg.get("enabled"), True):
            return {"available": False, "reason": "audio_event_bridge_disabled"}
        st = self.status(now=ts)
        if not st.get("available") or not st.get("fresh"):
            return {"available": False, "reason": st.get("reason") or "audio_event_stale", "status": st}
        owner_timeout = max(1.0, _as_float(self.cfg.get("owner_audio_timeout_s"), 45.0))
        owner_recent = self._owner_last_heard_ts > 0.0 and (ts - self._owner_last_heard_ts) <= owner_timeout
        audio_context = {
            "wakeword": bool(st.get("wakeword")),
            "speech": bool(st.get("speech")),
            "sound": bool(st.get("sound")),
            "silence": bool(st.get("silence")),
            "loud": bool(st.get("loud")),
            "owner_audio_present": bool(owner_recent),
            "sound_angle": st.get("sound_angle", 0.0),
            "suggested_pan": st.get("suggested_pan"),
            "transcript": str(st.get("transcript") or ""),
            "reason": st.get("reason", "audio.context"),
            "confidence": st.get("confidence", 0.0),
        }
        mood_overrides: Dict[str, Any] = {}
        needs_overrides: Dict[str, Any] = {}
        if audio_context["wakeword"]:
            needs_overrides["social"] = max(_as_float(needs_overrides.get("social"), 0.0), _as_float(self.cfg.get("wakeword_social"), 96.0))
            needs_overrides["stimulation"] = max(_as_float(needs_overrides.get("stimulation"), 0.0), 72.0)
            mood_overrides["curiosity"] = max(_as_float(mood_overrides.get("curiosity"), 0.0), 65.0)
        if audio_context["speech"]:
            needs_overrides["social"] = max(_as_float(needs_overrides.get("social"), 0.0), _as_float(self.cfg.get("speech_social"), 86.0))
            needs_overrides["stimulation"] = max(_as_float(needs_overrides.get("stimulation"), 0.0), 62.0)
        if audio_context["sound"]:
            needs_overrides["stimulation"] = max(_as_float(needs_overrides.get("stimulation"), 0.0), _as_float(self.cfg.get("sound_curiosity"), 76.0))
            mood_overrides["curiosity"] = max(_as_float(mood_overrides.get("curiosity"), 0.0), 72.0)
        if audio_context["silence"]:
            needs_overrides["stimulation"] = max(_as_float(needs_overrides.get("stimulation"), 0.0), _as_float(self.cfg.get("silence_boredom"), 58.0))
        if audio_context["loud"]:
            mood_overrides["fear"] = max(_as_float(mood_overrides.get("fear"), 0.0), _as_float(self.cfg.get("loud_fear"), 60.0))
        return {
            "available": True,
            "status": st,
            "audio_context": audio_context,
            "mood_overrides": mood_overrides,
            "needs_overrides": needs_overrides,
            "owner_present": bool(st.get("owner_present") or owner_recent),
            "owner_last_heard_ts": self._owner_last_heard_ts or None,
            "speech_busy": bool(st.get("speech_busy")),
        }

    def _push_history(self, item: Dict[str, Any]) -> None:
        compact = {
            "timestamp": item.get("timestamp"),
            "reason": item.get("reason"),
            "event_type": item.get("event_type", ""),
            "wakeword": item.get("wakeword", False),
            "speech": item.get("speech", False),
            "sound": item.get("sound", False),
            "silence": item.get("silence", False),
            "loud": item.get("loud", False),
        }
        self._history.append(compact)
        limit = int(_as_float(self.cfg.get("history_limit"), 20))
        self._history = self._history[-max(1, limit):]

    @staticmethod
    def _derive_event(wakeword: bool, speech: bool, sound: bool, silence: bool, loud: bool) -> str:
        if loud:
            return "loud_noise"
        if wakeword:
            return "wakeword"
        if speech:
            return "speech"
        if sound:
            return "sound"
        if silence:
            return "silence"
        return "audio"

    @staticmethod
    def _reason_for(*, wakeword: bool, speech: bool, sound: bool, silence: bool, loud: bool) -> str:
        if loud:
            return "audio.loud"
        if wakeword:
            return "audio.wakeword"
        if speech:
            return "audio.speech"
        if sound:
            return "audio.sound"
        if silence:
            return "audio.silence"
        return "audio.context"
