from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional


class RfidHandlerMixin:
    """RFID state tracking, authorization and validation methods."""

    _rfid_lock: threading.Lock
    _last_rfid: Optional[tuple[str, float]]
    cfg: Dict[str, Any]

    def get_last_rfid(self) -> Optional[Dict[str, Any]]:
        with self._rfid_lock:
            if not self._last_rfid:
                return None
            uid, ts = self._last_rfid
        return {"uid": uid, "seen_at": ts, "age_s": max(0.0, time.time() - ts)}

    def authorize_rfid(
        self, uid: Optional[str] = None, window_s: Optional[float] = None
    ) -> Dict[str, Any]:
        cfg = self.cfg.get("rfid", {}) or {}
        allowed = {self._normalize_uid(x) for x in cfg.get("allowed_uids", []) if x}
        window = float(
            window_s if window_s is not None else cfg.get("authorize_window_s", 8.0)
        )

        if uid:
            normalized_uid = self._normalize_uid(uid)
            age_s = None
        else:
            snap = self.get_last_rfid()
            if not snap:
                return {"authorized": False, "reason": "no_rfid"}
            normalized_uid = self._normalize_uid(snap.get("uid"))
            age_s = snap.get("age_s")
            if age_s is not None and age_s > window:
                return {
                    "authorized": False,
                    "uid": normalized_uid,
                    "age_s": age_s,
                    "reason": "stale",
                }

        if not normalized_uid:
            return {"authorized": False, "reason": "invalid_uid"}

        authorized = normalized_uid in allowed if allowed else False
        result: Dict[str, Any] = {"authorized": authorized, "uid": normalized_uid}
        if age_s is not None:
            result["age_s"] = age_s
        if not authorized and allowed:
            result["reason"] = "unauthorized"
        elif not allowed:
            result["reason"] = "no_allowed_uids"
        return result

    def _record_rfid(self, uid: Optional[str]) -> None:
        normalized = self._normalize_uid(uid)
        if not normalized:
            return
        with self._rfid_lock:
            self._last_rfid = (normalized, time.time())

    @staticmethod
    def _normalize_uid(uid: Optional[str]) -> Optional[str]:
        if not uid:
            return None
        cleaned = str(uid).strip().upper()
        return cleaned or None
