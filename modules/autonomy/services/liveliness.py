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

    def _modulate(self, emotion: str, amp: float, period: float, mode: str):
        """Hook for emotion-specific shaping (extended in a later change)."""
        return amp, period, mode

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


__all__ = ["LivelinessScheduler"]
