from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("autonomy.client_lights")

_LIGHTS_LOCKED = {"ok": False, "reason": "lights_locked"}


class ClientLightsMixin:
    """NeoPixel, OLED, and expressive lighting client helpers."""

    urls: Dict[str, str]
    request_timeouts: Dict[str, Any]
    _post: Callable[..., Any]
    _async_post: Callable[..., Any]

    def _led_policy(self) -> Any:
        arbiter = getattr(self, "_expression_arbiter", None)
        if arbiter is not None:
            return arbiter
        try:
            from modules.common.led_write_policy import get_shared_policy

            return get_shared_policy()
        except Exception:
            return None

    def _lights_gate(
        self,
        *,
        source: str = "autonomy",
        priority: Optional[float] = None,
        force: bool = False,
        ttl_s: Optional[float] = None,
        channel: str = "lights",
    ) -> bool:
        policy = self._led_policy()
        if policy is None:
            return True
        try:
            if channel == "oled":
                return bool(policy.claim_oled(str(source), force=bool(force), priority=priority, ttl_s=ttl_s))
            return bool(policy.claim_lights(str(source), force=bool(force), priority=priority, ttl_s=ttl_s))
        except Exception:
            return True

    @staticmethod
    def _parse_rgb(color: Any) -> tuple[int, int, int] | None:
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
            if "," in s:
                parts = [p.strip() for p in s.split(",")]
                if len(parts) >= 3:
                    try:
                        return (int(parts[0]) & 255, int(parts[1]) & 255, int(parts[2]) & 255)
                    except ValueError:
                        return None
        return None

    def animate_neopixel(
        self,
        effect: str,
        *,
        color=None,
        emotions=None,
        segment: str | None = None,
        iterations: int | None = None,
        lease_source: str = "autonomy",
    ) -> Any:
        url = self.urls.get("neopixel")
        if not url:
            return self.set_interaction_effect(str(effect), force=True, color=color, emotions=emotions, lease_source=lease_source)
        if not self._lights_gate(source=lease_source):
            return dict(_LIGHTS_LOCKED)
        payload: dict = {"name": str(effect or "PULSE").strip().upper() or "PULSE"}
        rgb = self._parse_rgb(color)
        if rgb is not None:
            payload["r"], payload["g"], payload["b"] = rgb
        if emotions:
            payload["emotions"] = [str(x) for x in emotions if str(x).strip()]
        if segment:
            payload["segment"] = str(segment)
        if iterations is not None:
            payload["iterations"] = int(iterations)
        return self._post("neopixel", "/animate", payload)

    def set_neopixel(self, effect: str, emotions=None, color=None, duration=None, lease_source: str = "autonomy") -> Any:
        name = str(effect or "PULSE").strip().upper() or "PULSE"
        duration_ms = 800
        if duration is not None:
            try:
                duration_ms = max(200, int(float(duration) * 1000))
            except (TypeError, ValueError):
                duration_ms = 800
        rgb = self._parse_rgb(color)
        if rgb is not None and self.urls.get("neopixel"):
            return self.animate_neopixel(name, color=rgb, emotions=emotions, lease_source=lease_source)
        return self.set_interaction_effect(
            name,
            duration_ms=duration_ms,
            force=True,
            color=color,
            emotions=emotions,
            lease_source=lease_source,
        )

    def emote_neopixel(self, emotions: list[str], duration: float = 0.25) -> Any:
        url = self.urls.get("neopixel")
        if not url or not emotions:
            return None
        if not self._lights_gate(ttl_s=float(duration) + 0.3):
            return dict(_LIGHTS_LOCKED)
        try:
            import requests
            params: dict = {"duration": float(duration)}
            if len(emotions) == 1:
                params["emotion"] = str(emotions[0])
            else:
                params["emotions"] = [str(e) for e in emotions if str(e).strip()]
            return requests.post(f"{url}/emote", params=params, timeout=float(self.request_timeouts.get("default_post_s", 1.0)))
        except Exception:
            return None

    def set_neopixel_segment_effect(self, segment: str, effect: str, color=None, emotions=None, iterations=None, lease_source: str = "autonomy") -> Any:
        name = str(effect or "PULSE").strip().upper() or "PULSE"
        rgb = self._parse_rgb(color)
        url = self.urls.get("neopixel")
        if url:
            return self.animate_neopixel(
                name,
                color=rgb,
                emotions=emotions,
                segment=str(segment or "").strip() or None,
                iterations=iterations,
                lease_source=lease_source,
            )
        return self.set_neopixel(name, emotions=emotions, color=color, lease_source=lease_source)

    def fill_neopixel_segment_color(self, segment: str, r: int, g: int, b: int) -> Any:
        url = self.urls.get("neopixel")
        if not url:
            return None
        if not self._lights_gate():
            return None
        try:
            import requests
            requests.post(
                f"{url}/fill",
                params={"r_": int(r), "g": int(g), "b": int(b), "segment": str(segment)},
                timeout=1.0,
            )
            return {"ok": True}
        except Exception as exc:
            logger.debug("Failed to fill neopixel segment color: %s", exc)
            return None

    def apply_neopixel_preset(self, name: str) -> Any:
        url = self.urls.get("neopixel")
        if not url:
            return None
        if not self._lights_gate():
            return None
        try:
            import requests
            resp = requests.post(f"{url}/preset/apply", params={"name": str(name)}, timeout=1.0)
            return resp.json() if resp.status_code == 200 else None
        except Exception as exc:
            logger.debug("Failed to apply neopixel preset: %s", exc)
            return None

    def fill_neopixel_color(self, r: int, g: int, b: int) -> None:
        url = self.urls.get("neopixel")
        if not url:
            return None
        if not self._lights_gate():
            return None
        try:
            import requests
            requests.post(
                f"{url}/fill",
                params={"r_": int(r), "g": int(g), "b": int(b)},
                timeout=1.0,
            )
        except Exception as exc:
            logger.debug("Failed to fill neopixel color: %s", exc)

    def fill_neopixel(self, r: int, g: int, b: int) -> None:
        if not self._lights_gate():
            return None
        payload = {"effect": "solid", "color": [r, g, b]}
        try:
            self._post("gateway", "/api/neopixel/effect", payload)
        except Exception:
            pass

    def set_interaction_effect(
        self,
        name: str,
        duration_ms: int = 800,
        force: bool = False,
        color=None,
        emotions=None,
        lease_source: str = "autonomy",
    ) -> Any:
        if not self._lights_gate(
            ttl_s=max(0.8, float(duration_ms) / 1000.0 + 0.3),
            source=lease_source,
            force=bool(force),
        ):
            return dict(_LIGHTS_LOCKED)
        payload: dict = {
            "name": str(name),
            "duration_ms": int(duration_ms),
            "force": bool(force),
        }
        rgb = self._parse_rgb(color)
        if rgb is not None:
            payload["r"], payload["g"], payload["b"] = rgb
        elif color is not None:
            payload["color"] = color
        if emotions:
            payload["emotions"] = [str(x) for x in emotions if str(x).strip()]
        return self._post("interactions", "/effect", payload)

    def set_interaction_base(self, name: str, color=None) -> Any:
        if not self._lights_gate():
            return dict(_LIGHTS_LOCKED)
        payload = {"name": str(name)}
        if color is not None:
            payload["color"] = color
        return self._post("interactions", "/base", payload)

    def apply_oled_face(self, mode: str = "animation", name: str = "love") -> Any:
        return self._post("oled_faces", "/manual", {"mode": mode, "name": name})

    def set_oled_stt_text(self, text: str, duration_s: float = 4.5) -> Any:
        return self._post("oled_faces", "/stt_text", {"text": text, "duration_s": duration_s})

    def oled_show(self, name: str) -> Any:
        return self._post("oled_faces", "/manual", {"mode": "bitmap", "name": str(name)})

    def oled_anim(self, name: str) -> Any:
        return self._post("oled_faces", "/manual", {"mode": "animation", "name": str(name)})

    def oled_stop(self) -> Any:
        return self._post("oled_faces", "/manual", {"mode": "bitmap", "name": "normal"})

    def oled_logo(self) -> Any:
        return self._post("oled_faces", "/manual", {"mode": "logo", "name": "logo"})

    def express_emotion(
        self,
        emotion: str,
        *,
        intensity: float = 1.0,
        duration_s: float = 3.0,
        modalities: Optional[list] = None,
        text: Optional[str] = None,
        language: str = "tr",
        force: bool = False,
    ) -> Any:
        payload = {
            "emotion": str(emotion),
            "intensity": float(intensity),
            "duration_s": float(duration_s),
            "modalities": list(modalities or ["leds", "oled", "ears"]),
            "language": str(language),
            "force": bool(force),
        }
        if text:
            payload["text"] = str(text)
        return self._post("expression", "/express", payload)

    async def async_express_emotion(
        self,
        emotion: str,
        intensity: float = 1.0,
        duration_s: float = 3.0,
        modalities: list[str] | None = None,
        text: str | None = None,
        language: str = "tr",
    ) -> dict:
        mods = list(modalities) if modalities else ["leds", "oled", "voice", "head"]
        return await self._async_post(
            "gateway", "/expression/express",
            json={
                "emotion": emotion,
                "intensity": min(2.0, max(0.1, float(intensity))),
                "duration_s": min(30.0, max(0.5, float(duration_s))),
                "modalities": mods,
                "text": text,
                "language": str(language or "tr"),
            },
            timeout=3.0,
        )

    async def async_emote_neopixel(self, emotions: list[str], duration: float = 0.25) -> dict:
        return await self._async_post(
            "neopixel", "/emote",
            params={"duration": duration, "emotions": emotions},
            timeout=2.0,
        )

    async def async_set_neopixel(self, effect: str, color=None, emotions=None, duration=None) -> dict:
        payload = {"name": str(effect or "PULSE").strip().upper()}
        if color is not None:
            rgb = self._parse_rgb(color)
            if rgb is not None:
                payload["r"], payload["g"], payload["b"] = rgb
        if emotions:
            payload["emotions"] = [str(e) for e in emotions]
        if duration is not None:
            payload["duration"] = float(duration)
        return await self._async_post("neopixel", "/animate", json=payload)
