from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI

from .config_loader import load_config
from .services.mapper import FaceMapper, OledAction
from .services.pi_ssd1306_driver import PiSsd1306Driver
from .api.router import get_router


class xOledFacesService:
    def __init__(self, state_store: Any = None, config_overrides: Optional[Dict[str, Any]] = None):
        self.cfg = load_config(overrides=config_overrides)
        self.state_store = state_store
        self.mapper = FaceMapper(self.cfg)
        self.display = PiSsd1306Driver(self.cfg.get("display") if isinstance(self.cfg.get("display"), dict) else {})

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_operational = None
        self._last_emotions = None
        self._last_sent: Optional[tuple[str, str]] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.display.begin()
        self._apply(self._boot_action())
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
            "display": self.display.status(),
            "catalog": {
                "bitmaps": self.mapper.catalog_bitmaps,
                "animations": self.mapper.catalog_animations,
            },
        }

    def on_interaction_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if not self.cfg.get("enabled", True):
            return
        action = self.mapper.from_interaction_event(event_type)
        self._apply(action)

    def apply_manual(self, mode: str, name: str) -> Dict[str, Any]:
        action = OledAction(mode=str(mode), name=str(name))
        ok = self._apply(action)
        return {"ok": ok, "mode": action.mode, "name": action.name}

    def _loop(self) -> None:
        interval_s = float(self.cfg.get("poll_interval_s", 0.7))
        while not self._stop.is_set():
            self._sync_from_state_store()
            time.sleep(max(0.05, interval_s))

    def _sync_from_state_store(self) -> None:
        if self.state_store is None or not hasattr(self.state_store, "get"):
            return
        try:
            state = self.state_store.get() or {}
        except Exception:
            return

        operational = str(state.get("operational", "idle")).strip().lower()
        emotions = [str(x).strip().lower() for x in (state.get("emotions") or []) if str(x).strip()]

        if emotions != self._last_emotions and emotions:
            self._last_emotions = list(emotions)
            self._apply(self.mapper.from_emotions(emotions))
            return

        if operational != self._last_operational:
            self._last_operational = operational
            self._apply(self.mapper.from_operational(operational))

    def _boot_action(self) -> OledAction:
        boot_mode = str(self.cfg.get("boot", {}).get("mode", "logo"))
        boot_name = str(self.cfg.get("boot", {}).get("name", "logo"))
        return OledAction(mode=boot_mode, name=boot_name)

    def _apply(self, action: OledAction) -> bool:
        if not bool(self.cfg.get("enabled", True)):
            return False
        mode = action.mode.strip().lower()
        name = action.name.strip().lower()
        sent_key = (mode, name)
        if sent_key == self._last_sent and mode != "animation":
            return True
        try:
            if mode == "logo":
                self.display.stop_animation()
                ok = self.display.show_logo()
            elif mode == "animation":
                ok = self.display.start_animation(name)
            elif mode == "test":
                self.display.stop_animation()
                ok = self.display.show_test_pattern()
            else:
                self.display.stop_animation()
                ok = self.display.show_bitmap(name)
            if not ok:
                return False
            self._last_sent = sent_key
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
