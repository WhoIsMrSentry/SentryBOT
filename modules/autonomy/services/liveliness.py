"""Mood-driven firmware liveliness scheduler.

Turns the robot's mood into parameters for the firmware-native idle motion
(breathing / micro-movement) and decides *when* to (re)send a liveliness command
to the Arduino — only on meaningful change or after a refresh interval, so the
serial link isn't flooded. Pure and deterministic so it can be unit-tested
without hardware; the brain feeds it mood and forwards the plan to the client.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class LivelinessScheduler:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config if isinstance(config, dict) else {}
        self.enabled = bool(cfg.get("enabled", True))
        self.base_amplitude_deg = float(cfg.get("amplitude_deg", 4.0))
        self.base_period_ms = int(cfg.get("period_ms", 4500))
        self.refresh_interval_s = float(cfg.get("refresh_interval_s", 20.0))
        self.max_amplitude_deg = float(cfg.get("max_amplitude_deg", 12.0))
        self._last_sent_ts = 0.0
        self._last_params: Optional[Dict[str, Any]] = None

    def plan(self, *, energy: float = 50.0, dominant_emotion: str = "neutral") -> Dict[str, Any]:
        """Compute liveliness parameters from current mood.

        Base behaviour: a calm breathing whose amplitude scales gently with
        energy. Emotion-specific shaping is layered on in :meth:`_modulate`.
        """
        e = _clamp(float(energy), 0.0, 100.0)
        amp = self.base_amplitude_deg * (0.6 + (e / 100.0) * 0.8)
        period = float(self.base_period_ms)
        mode = "breathe"
        amp, period, mode = self._modulate(dominant_emotion, amp, period, mode)
        amp = _clamp(amp, 0.0, self.max_amplitude_deg)
        return {"mode": mode, "amplitude_deg": round(amp, 1), "period_ms": int(period)}

    # Per-canonical-emotion shaping: (amplitude_mul, period_mul, mode).
    # period_mul < 1 => faster motion. Resolved through the shared vocab so
    # aliases map consistently with eyes/LEDs/voice.
    _EMOTION_SHAPE = {
        "excitement": (1.6, 0.6, "micro"),
        "joy": (1.3, 0.8, "breathe"),
        "surprise": (1.5, 0.55, "micro"),
        "curiosity": (1.2, 0.75, "micro"),
        "love": (1.1, 0.9, "breathe"),
        "fear": (1.4, 0.45, "micro"),
        "anger": (1.5, 0.5, "micro"),
        "furious": (1.7, 0.4, "micro"),
        "sadness": (0.6, 1.4, "breathe"),
        "worried": (0.9, 0.7, "micro"),
        "tired": (0.5, 1.6, "breathe"),
        "bored": (0.7, 1.3, "breathe"),
        "neutral": (1.0, 1.0, "breathe"),
    }

    def _modulate(self, emotion: str, amp: float, period: float, mode: str):
        """Shape amplitude/tempo/mode by the dominant emotion."""
        try:
            from modules.common.emotion_vocab import get_vocab

            canon = get_vocab().canonical(emotion)
        except Exception:
            canon = str(emotion or "neutral").strip().lower()
        amp_mul, period_mul, shaped_mode = self._EMOTION_SHAPE.get(canon, (1.0, 1.0, mode))
        period = _clamp(period * period_mul, 800.0, 12000.0)
        return amp * amp_mul, period, shaped_mode

    @staticmethod
    def _params_differ(a: Optional[Dict[str, Any]], b: Optional[Dict[str, Any]]) -> bool:
        if a is None or b is None:
            return True
        if a.get("mode") != b.get("mode"):
            return True
        # Treat sub-degree / sub-100ms wobble as "same" to avoid chatty resends.
        if abs(float(a.get("amplitude_deg", 0)) - float(b.get("amplitude_deg", 0))) >= 1.0:
            return True
        if abs(int(a.get("period_ms", 0)) - int(b.get("period_ms", 0))) >= 250:
            return True
        return False

    def due(self, now: float, params: Dict[str, Any]) -> bool:
        """Whether a (re)send is warranted right now."""
        if not self.enabled:
            return False
        if self._params_differ(params, self._last_params):
            return True
        return (now - self._last_sent_ts) >= self.refresh_interval_s

    def mark_sent(self, now: float, params: Dict[str, Any]) -> None:
        self._last_sent_ts = now
        self._last_params = dict(params)

    def record_interaction(self) -> None:
        """Mark an active interaction event."""
        self._last_sent_ts = 0.0


__all__ = ["LivelinessScheduler"]
