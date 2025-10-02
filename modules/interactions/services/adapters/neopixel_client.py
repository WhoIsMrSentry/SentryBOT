from __future__ import annotations

import time
from typing import Any, Dict, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore


class NeoHttpClient:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def _post(self, path: str, json: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> None:
        if requests is None:
            return
        try:
            requests.post(self.base + path, json=json, params=params, timeout=1.5)
        except Exception:
            pass

    # Basic controls
    def clear(self) -> None:
        self._post("/clear")

    def fill(self, r: int, g: int, b: int) -> None:
        self._post("/fill", params={"r_": r, "g": g, "b": b})

    def animate(self, name: str, emotions: Optional[list[str]] = None, iterations: Optional[int] = None) -> None:
        params: Dict[str, Any] = {"name": name}
        if emotions:
            params["emotions"] = emotions
        if iterations is not None:
            params["iterations"] = iterations
        self._post("/animate", params=params)

    # Friendly helpers
    def set_base(self, name: str, color: Optional[str | tuple[int, int, int]] = None, speed: Optional[str] = None) -> None:
        # Map to animate with optional emotions: if color hex provided, we cannot pass directly; fallback to simple fill
        if name.upper() in {"BREATHE", "PULSE", "COMET", "METEOR", "RAINBOW", "RAINBOW_CYCLE", "THEATER_CHASE"}:
            self.animate(name)
        elif color and isinstance(color, tuple):
            r, g, b = color
            self.fill(r, g, b)
        else:
            self.animate(name)

    def play_effect(self, name: str, duration_ms: int = 800, color: Optional[str | tuple[int, int, int]] = None) -> None:
        # Trigger an animation for a brief time, then clear to allow base to repaint next tick
        self.set_base(name, color=color)
        time.sleep(max(0.0, duration_ms / 1000.0))
        # Do not clear harshly; let engine repaint base on next cycle


class NoOpNeoClient:
    def clear(self) -> None:  # pragma: no cover
        pass

    def fill(self, r: int, g: int, b: int) -> None:  # pragma: no cover
        pass

    def animate(self, name: str, emotions: Optional[list[str]] = None, iterations: Optional[int] = None) -> None:  # pragma: no cover
        pass

    def set_base(self, name: str, color: Optional[str | tuple[int, int, int]] = None, speed: Optional[str] = None) -> None:  # pragma: no cover
        pass

    def play_effect(self, name: str, duration_ms: int = 800, color: Optional[str | tuple[int, int, int]] = None) -> None:  # pragma: no cover
        pass
