"""Procedural Pip-style face renderer backed by Pi SSD1306 I2C."""
from __future__ import annotations

from typing import Any, Dict, Optional

from .eyes.engine import EyeEngine
from .legacy_map import FaceCommand, resolve_animation, resolve_bitmap, resolve_logo
from .pi_ssd1306_driver import PiSsd1306Driver


class FaceRenderer:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        display_cfg = dict(cfg or {})
        self._fps = int(display_cfg.pop("fps", 24))
        self._driver = PiSsd1306Driver(display_cfg)
        self._engine: Optional[EyeEngine] = None

    def begin(self) -> bool:
        ok = self._driver.begin()
        if not ok:
            return False
        self._engine = EyeEngine(
            self._driver.show_pil_image,
            width=self._driver.width,
            height=self._driver.height,
            fps=self._fps,
        )
        self._engine.start()
        return True

    def close(self) -> None:
        if self._engine is not None:
            self._engine.stop()
            self._engine = None
        self._driver.close()

    def status(self) -> Dict[str, Any]:
        st = dict(self._driver.status())
        st["renderer"] = "pip_eyes"
        st["fps"] = self._fps
        st["engine_running"] = bool(self._engine and self._engine._thread and self._engine._thread.is_alive())
        return st

    def stop_loops(self) -> None:
        if self._engine is not None:
            self._engine.set_activity("idle")

    def show_test_pattern(self) -> bool:
        self.stop_loops()
        return self._driver.show_test_pattern()

    def apply(self, mode: str, name: str) -> bool:
        if self._engine is None and not self._driver.status().get("ok"):
            return False
        if self._engine is None:
            return False

        m = str(mode or "bitmap").strip().lower()
        if m == "test":
            return self.show_test_pattern()
        if m == "logo":
            return self._run(resolve_logo())
        if m == "animation":
            return self._run(resolve_animation(name))
        return self._run(resolve_bitmap(name))

    def _run(self, cmd: FaceCommand) -> bool:
        eng = self._engine
        if eng is None:
            return False
        try:
            if cmd.activity is not None:
                eng.set_activity(cmd.activity)
            else:
                eng.set_activity("idle")
            if cmd.mood is not None:
                eng.set_mood(cmd.mood)
            if cmd.gesture:
                eng.play_gesture(cmd.gesture)
            return True
        except Exception:
            return False
