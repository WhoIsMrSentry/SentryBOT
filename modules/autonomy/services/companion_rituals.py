from __future__ import annotations

import datetime
import time
from typing import Any, Dict, Optional


class CompanionRituals:
    """Low-frequency social rituals to improve companion continuity.

    When a :class:`modules.social_db.SocialDB` instance is registered, the
    "morning greeting done" flag is persisted in the ``rituals`` table so the
    ritual is not repeated after a restart on the same day.
    """

    def __init__(self, cfg: Dict[str, Any], social_db: Optional[Any] = None) -> None:
        self.cfg = cfg if isinstance(cfg, dict) else {}
        self.enabled = bool(self.cfg.get("enabled", True))
        self.min_absence_s = float(self.cfg.get("owner_return_min_absence_s", 180.0))
        self.owner_return_cooldown_s = float(self.cfg.get("owner_return_cooldown_s", 300.0))
        self.morning_window = tuple(self.cfg.get("morning_window_h", [6, 11]))  # inclusive start/end
        if social_db is None:
            try:
                from modules.social_db import get_default as _social_default  # type: ignore

                social_db = _social_default()
            except Exception:
                social_db = None
        self._social_db = social_db
        self._last_owner_return_ts: float = 0.0
        self._owner_absent_since: float = time.time()
        self._owner_prev_present: bool = False
        self._morning_done_day: str = ""

    def propose(self, now_ts: float, owner_present: bool, is_sleeping: bool) -> Optional[Dict[str, Any]]:
        if not self.enabled or is_sleeping:
            self._update_owner_presence(now_ts, owner_present)
            return None

        proposal = self._propose_morning(owner_present)
        if proposal:
            self._update_owner_presence(now_ts, owner_present)
            return proposal

        proposal = self._propose_owner_return(now_ts, owner_present)
        self._update_owner_presence(now_ts, owner_present)
        return proposal

    def _propose_morning(self, owner_present: bool) -> Optional[Dict[str, Any]]:
        if not owner_present:
            return None
        now = datetime.datetime.now()
        day_key = now.strftime("%Y-%m-%d")
        if self._morning_done_day == day_key:
            return None
        if self._social_db is not None:
            try:
                if self._social_db.rituals.is_done("morning", day=day_key):
                    self._morning_done_day = day_key
                    return None
            except Exception:
                pass
        start_h, end_h = self._safe_window()
        if not (start_h <= now.hour <= end_h):
            return None
        self._morning_done_day = day_key
        if self._social_db is not None:
            try:
                self._social_db.rituals.mark_done(
                    "morning",
                    day=day_key,
                    payload={"hour": now.hour, "minute": now.minute},
                )
            except Exception:
                pass
        return {
            "text": "Gunaydin, bugun nasil hissettigini merak ediyorum.",
            "emotion": "joy",
            "event": "companion.ritual.morning",
        }

    def _propose_owner_return(self, now_ts: float, owner_present: bool) -> Optional[Dict[str, Any]]:
        if not owner_present:
            return None
        if self._owner_prev_present:
            return None
        absence_s = max(0.0, now_ts - self._owner_absent_since)
        if absence_s < self.min_absence_s:
            return None
        if (now_ts - self._last_owner_return_ts) < self.owner_return_cooldown_s:
            return None
        self._last_owner_return_ts = now_ts
        if self._social_db is not None:
            try:
                self._social_db.rituals.mark_done(
                    "owner_return",
                    payload={"ts": now_ts, "absence_s": absence_s},
                )
            except Exception:
                pass
        return {
            "text": "Tekrar hos geldin, seni gormek iyi hissettirdi.",
            "emotion": "joy",
            "event": "companion.ritual.owner_return",
        }

    def _update_owner_presence(self, now_ts: float, owner_present: bool) -> None:
        if not owner_present:
            if self._owner_prev_present:
                self._owner_absent_since = now_ts
            self._owner_prev_present = False
            return
        self._owner_prev_present = True

    def _safe_window(self) -> tuple[int, int]:
        try:
            start_h = int(self.morning_window[0])
            end_h = int(self.morning_window[1])
        except Exception:
            return (6, 11)
        start_h = max(0, min(23, start_h))
        end_h = max(0, min(23, end_h))
        if start_h > end_h:
            return (6, 11)
        return (start_h, end_h)
