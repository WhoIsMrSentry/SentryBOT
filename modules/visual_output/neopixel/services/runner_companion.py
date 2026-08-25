from __future__ import annotations

import logging
import queue
from typing import Any, Optional

logger = logging.getLogger("neopixel.runner_companion")


class RunnerCompanionMixin:
    """Companion LED modes and semantic light state integration."""

    driver: Any
    _companion: Any
    _frame_lock: Any
    _animation_lock: Any
    _animation_generation: int
    _active_animation: str
    _animate_queue: queue.Queue

    def companion_set_mode(self, mode: str) -> bool:
        if self._companion is None:
            return False
        active = str(mode or "").strip().lower() not in {"", "off"}
        if active and hasattr(self, "_cancel_animations"):
            self._cancel_animations()
        ok = self._companion.set_mode(mode)
        if active and ok:
            try:
                with self._frame_lock:
                    self.driver.clear()
            except Exception:
                pass
        return bool(ok)

    def companion_is_active(self) -> bool:
        if self._companion is None:
            return False
        return self._companion.is_active

    def companion_set_eye_color(self, r: int, g: int, b: int) -> bool:
        if self._companion is None:
            return False
        self._companion.set_eye_color((int(r) & 255, int(g) & 255, int(b) & 255))
        return True

    def companion_apply_semantic(self, semantic: str, *, revision: str = "", duration_ms: Optional[int] = None) -> bool:
        if self._companion is None:
            return False
        if hasattr(self, "_cancel_animations"):
            self._cancel_animations()
        return self._companion.apply_semantic(semantic, revision=revision, duration_ms=duration_ms)

    def companion_semantic_catalog(self) -> dict[str, Any]:
        if self._companion is None:
            return {}
        return self._companion.semantic_catalog()

    def companion_status(self) -> dict[str, Any]:
        if self._companion is None:
            return {"enabled": False, "mode": "off"}
        with self._animation_lock:
            generation = self._animation_generation
            active_animation = self._active_animation
        return {
            "enabled": True,
            **self._companion.status(),
            "animation_generation": generation,
            "active_animation": active_animation,
            "animation_queue_size": self._animate_queue.qsize(),
        }
