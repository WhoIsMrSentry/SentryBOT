from __future__ import annotations

import time
import logging
from typing import Any, Dict, Optional

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore


logger = logging.getLogger("interactions.neopixel_client")


def _normalize_color(color: Any) -> Optional[tuple[int, int, int]]:
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        try:
            return (int(color[0]) & 255, int(color[1]) & 255, int(color[2]) & 255)
        except (TypeError, ValueError):
            return None
    if isinstance(color, str):
        s = color.strip()
        if s.startswith("#") and len(s) >= 7:
            try:
                v = int(s[1:7], 16)
                return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
            except ValueError:
                return None
    return None


class NeoHttpClient:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")

    def _post(self, path: str, json: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> None:
        if requests is None:
            logger.warning("neopixel http client disabled: requests not available")
            return
        try:
            resp = requests.post(self.base + path, json=json, params=params, timeout=1.5)
            if resp.status_code >= 400:
                logger.warning("neopixel request failed: %s %s -> %s", "POST", self.base + path, resp.status_code)
        except Exception as exc:
            logger.warning("neopixel request error: %s %s (%s)", "POST", self.base + path, exc)

    # Basic controls
    def clear(self) -> None:
        self._post("/clear")

    def fill(self, r: int, g: int, b: int) -> None:
        self._post("/fill", params={"r_": r, "g": g, "b": b})

    def animate(
        self,
        name: str,
        emotions: Optional[list[str]] = None,
        iterations: Optional[int] = None,
        color: Optional[str | tuple[int, int, int]] = None,
    ) -> None:
        payload: Dict[str, Any] = {"name": name}
        rgb = _normalize_color(color)
        if rgb is not None:
            payload["r"], payload["g"], payload["b"] = rgb
        if emotions:
            payload["emotions"] = emotions
        if iterations is not None:
            payload["iterations"] = iterations
        self._post("/animate", json=payload)

    # Friendly helpers
    def set_base(self, name: str, color: Optional[str | tuple[int, int, int]] = None, speed: Optional[str] = None) -> None:
        rgb = _normalize_color(color)
        if rgb is not None:
            self.animate(name, color=rgb)
        else:
            self.animate(name)

    def play_effect(
        self,
        name: str,
        duration_ms: int = 800,
        color: Optional[str | tuple[int, int, int]] = None,
        emotions: Optional[list[str]] = None,
    ) -> None:
        self.set_base(name, color=color)
        time.sleep(max(0.0, duration_ms / 1000.0))

    def companion_mode(self, mode: str, eye_color: Any = None) -> None:
        payload: Dict[str, Any] = {"mode": str(mode)}
        if eye_color is not None:
            rgb = _normalize_color(eye_color)
            if rgb is not None:
                payload["eye_color"] = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        self._post("/companion/mode", json=payload)

    def companion_vu(self, level: float) -> None:
        self._post("/companion/vu", json={"level": float(level)})


class NoOpNeoClient:
    def clear(self) -> None:  # pragma: no cover
        pass

    def fill(self, r: int, g: int, b: int) -> None:  # pragma: no cover
        pass

    def animate(
        self,
        name: str,
        emotions: Optional[list[str]] = None,
        iterations: Optional[int] = None,
        color: Optional[str | tuple[int, int, int]] = None,
    ) -> None:  # pragma: no cover
        pass

    def set_base(self, name: str, color: Optional[str | tuple[int, int, int]] = None, speed: Optional[str] = None) -> None:  # pragma: no cover
        pass

    def play_effect(
        self,
        name: str,
        duration_ms: int = 800,
        color: Optional[str | tuple[int, int, int]] = None,
        emotions: Optional[list[str]] = None,
    ) -> None:  # pragma: no cover
        pass
