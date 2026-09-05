from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("speech.sound_tracking")


class SpeechSoundTrackingMixin:
    """Sound source tracking and pan/tilt servo sender routing."""

    cfg: Dict[str, Any]
    _pan: Any
    _tracking: bool
    _last_angle: Optional[float]
    _head_arbiter: Any

    def track_start(self) -> None:
        self._tracking = True
        self._pan.start()

    def track_stop(self) -> None:
        self._tracking = False
        self._pan.stop()

    def track_status(self) -> dict:
        st = self._pan.status()
        st["tracking"] = self._tracking
        st["angle"] = self._last_angle
        return st

    def attach_head_arbiter(self, arbiter: Any) -> None:
        self._head_arbiter = arbiter

    def _send_pan(self, angle_deg: float) -> None:
        pt_cfg = self.cfg.get("pan_tilt", {}) if isinstance(self.cfg.get("pan_tilt"), dict) else {}
        if self._head_arbiter is not None and hasattr(self._head_arbiter, "move"):
            try:
                res = self._head_arbiter.move(
                    pan=float(angle_deg),
                    tilt=float(pt_cfg.get("center_tilt_deg", 90.0)),
                    source="sound_direction",
                    priority=int(pt_cfg.get("arbiter_priority", 60)),
                )
                if res and res.get("ok"):
                    return
            except Exception as exc:
                logger.debug("direct head arbiter pan move failed: %s", exc)

        if bool(pt_cfg.get("use_head_arbiter", True)):
            try:
                import requests
                from modules.gateway.url import gateway_url, resolve_gateway_base_url

                base = resolve_gateway_base_url(self.cfg)
                url = gateway_url(base, "/vlm/head/move")
                requests.post(
                    url,
                    json={
                        "pan": float(angle_deg),
                        "tilt": float(pt_cfg.get("center_tilt_deg", 90.0)),
                        "source": "sound_direction",
                        "priority": int(pt_cfg.get("arbiter_priority", 60)),
                    },
                    timeout=0.25,
                )
                return
            except Exception as exc:
                # No raw set_servo fallback here: an ungated servo write would
                # bypass the head arbiter entirely (R2). Drop this pan update.
                logger.debug("sound-direction pan dropped without arbiter route: %s", exc)
            return
