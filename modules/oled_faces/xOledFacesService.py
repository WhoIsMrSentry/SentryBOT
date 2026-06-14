from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI

from .config_loader import load_config
from .services.mapper import FaceMapper, OledAction
from .services.face_renderer import FaceRenderer
from .services.face_coordinator import FaceCoordinator
from .services.legacy_map import resolve_mood
from .api.router import get_router


class xOledFacesService:
    def __init__(
        self,
        state_store: Any = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        expression_arbiter: Any = None,
    ):
        self.cfg = load_config(overrides=config_overrides)
        self.state_store = state_store
        self._expression_arbiter = expression_arbiter
        self.mapper = FaceMapper(self.cfg)
        self.coordinator = FaceCoordinator(self.mapper, self.cfg)
        display_cfg = self.cfg.get("display") if isinstance(self.cfg.get("display"), dict) else {}
        self.display = FaceRenderer(display_cfg)

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_operational: Optional[str] = None
        self._last_emotions: Optional[List[str]] = None
        self._last_sent: Optional[tuple[str, str]] = None
        self._last_apply_ts: float = 0.0
        self._active_hold_until: float = 0.0
        self._active_priority: int = 0
        self._last_event_ts: Dict[str, float] = {}
        self._last_mode: str = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.display.begin()
        self._apply(self._boot_action(), priority=80, force=True)
        self._thread = threading.Thread(target=self._loop, name="oled-faces", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self.display.close()

    def status(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": bool(self.cfg.get("enabled", True)),
            "has_display": bool(self.display.status().get("ok", False)),
            "has_state_store": self.state_store is not None,
            "last_sent": self._last_sent,
            "session_active": self.coordinator.session_active(),
            "display": self.display.status(),
            "catalog": {
                "bitmaps": self.mapper.catalog_bitmaps,
                "animations": self.mapper.catalog_animations,
            },
        }

    def on_interaction_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if not self.cfg.get("enabled", True):
            return
        if self._event_rate_limited(event_type):
            return
        action = self.mapper.from_interaction_event(event_type)
        pri = self._priority_for(source="event", event_type=event_type, action=action)
        baseline = self._baseline_from_store() if str(event_type or "").strip().lower() == "speech.end" else None
        decision = self.coordinator.on_event(event_type, action, pri, baseline=baseline)
        if decision.apply:
            self._apply(decision.action, priority=decision.priority)

    def apply_manual(self, mode: str, name: str) -> Dict[str, Any]:
        action = OledAction(mode=str(mode), name=str(name))
        ok = self._apply(action, priority=100, force=True)
        return {"ok": ok, "mode": action.mode, "name": action.name}

    def _loop(self) -> None:
        interval_s = float(self.cfg.get("poll_interval_s", 0.7))
        while not self._stop.is_set():
            self._maybe_clear_activity()
            self._sync_from_state_store()
            time.sleep(max(0.05, interval_s))

    def _maybe_clear_activity(self) -> None:
        now = time.time()
        if self._last_mode != "animation":
            return
        if not self.coordinator.should_clear_activity(now, self._active_hold_until):
            return
        self.display.stop_loops()
        self._last_mode = ""

    def _sync_from_state_store(self) -> None:
        if self.state_store is None or not hasattr(self.state_store, "get"):
            return
        try:
            state = self.state_store.get() or {}
        except Exception:
            return

        operational = str(state.get("operational", "idle")).strip().lower()
        emotions = [str(x).strip().lower() for x in (state.get("emotions") or []) if str(x).strip()]

        op_changed = operational != self._last_operational
        emo_changed = emotions != self._last_emotions

        decision = self.coordinator.from_state(
            operational,
            emotions,
            op_changed=op_changed,
            emo_changed=emo_changed,
        )
        if self._last_operational is None or op_changed:
            self._last_operational = operational
        if self._last_emotions is None or emo_changed:
            self._last_emotions = list(emotions)

        if decision is None or not decision.apply:
            return
        event_key = operational if decision.source == "state" else f"emotion:{emotions[0]}" if emotions else operational
        pri = self._priority_for(source=decision.source, event_type=event_key, action=decision.action)
        self._apply(decision.action, priority=pri)

    def _baseline_from_store(self) -> Optional[OledAction]:
        if self.state_store is None or not hasattr(self.state_store, "get"):
            return None
        try:
            state = self.state_store.get() or {}
        except Exception:
            return None
        emotions = [str(x).strip().lower() for x in (state.get("emotions") or []) if str(x).strip()]
        if emotions:
            return self.mapper.from_emotions(emotions)
        idle = str(self.cfg.get("idle_bitmap", "normal"))
        return OledAction(mode="bitmap", name=idle)

    def _boot_action(self) -> OledAction:
        boot_mode = str(self.cfg.get("boot", {}).get("mode", "logo"))
        boot_name = str(self.cfg.get("boot", {}).get("name", "logo"))
        return OledAction(mode=boot_mode, name=boot_name)

    def _event_rate_limited(self, event_type: str) -> bool:
        now = time.time()
        cooldown_s = float(self.cfg.get("event_cooldown_s", 0.8))
        key = str(event_type or "").strip().lower()
        if not key:
            return False
        if key.startswith("emotion:"):
            cooldown_s = float(self.cfg.get("emotion_hold_s", 2.5))
        last = float(self._last_event_ts.get(key, 0.0))
        if now - last < max(0.05, cooldown_s):
            return True
        self._last_event_ts[key] = now
        return False

    def _priority_for(self, source: str, event_type: str, action: OledAction) -> int:
        key = str(event_type or "").strip().lower()
        pri_map = self.cfg.get("priority_map", {}) if isinstance(self.cfg.get("priority_map"), dict) else {}
        if key in pri_map:
            try:
                return int(pri_map.get(key))
            except Exception:
                pass
        mode = str(action.mode or "").strip().lower()
        if source == "event":
            if "error" in key or "warning" in key or "owner.locked" in key:
                return 90
            if mode == "animation":
                return 70
            return 65
        if source == "emotion":
            if "fear" in key or "angry" in key or "furious" in key:
                return 85
            return 60
        if source == "state":
            return 40 if mode == "bitmap" else 50
        return 50

    def _apply(self, action: OledAction, priority: int = 50, force: bool = False) -> bool:
        if not bool(self.cfg.get("enabled", True)):
            return False
        if self._expression_arbiter is not None:
            try:
                if not self._expression_arbiter.claim_oled("oled_faces", force=bool(force)):
                    return False
            except Exception:
                pass
        now = time.time()
        mode = action.mode.strip().lower()
        name = action.name.strip().lower()
        sent_key = (mode, name)

        min_interval = float(self.cfg.get("min_switch_interval_s", 0.45))
        if not force and sent_key != self._last_sent and (now - self._last_apply_ts) < max(0.03, min_interval):
            return False

        if not force and now < self._active_hold_until and priority < self._active_priority and sent_key != self._last_sent:
            return False

        if sent_key == self._last_sent and mode != "animation":
            return True
        try:
            ok = self.display.apply(mode, name)
            if not ok:
                return False
            self._last_sent = sent_key
            self._last_apply_ts = now
            self._active_priority = int(priority)
            self._last_mode = mode
            if mode == "animation":
                self._active_hold_until = now + max(0.2, float(self.cfg.get("animation_hold_s", 1.2)))
            else:
                self._active_hold_until = now + max(0.05, float(self.cfg.get("bitmap_hold_s", 0.25)))
            if mode == "bitmap":
                self.coordinator.note_applied_mood(resolve_mood(name))
            return True
        except Exception:
            return False


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    svc = xOledFacesService(config_overrides=cfg)
    app = FastAPI(title="OLED Faces Service")
    app.include_router(get_router(svc))
    return app


if __name__ == "__main__":
    import uvicorn

    cfg = load_config(None)
    uvicorn.run(create_app(), host=str(cfg.get("server", {}).get("host", "0.0.0.0")), port=int(cfg.get("server", {}).get("port", 8102)))
