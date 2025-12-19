from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import httpx


@dataclass
class CommandResult:
    text: Optional[str] = None
    photo: Optional[bytes] = None


class CommandRouter:
    """Map Telegram commands to HTTP calls on other modules."""

    def __init__(self, base_url: str, timeout: float = 4.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def handle(self, client: httpx.AsyncClient, text: str) -> Optional[CommandResult]:
        parts = text.strip().split()
        if not parts:
            return None
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd in ("/help", "/h"):
                return CommandResult(text=self._help())
            if cmd == "/status":
                return CommandResult(text=await self._status(client))
            if cmd in ("/snap", "/snapshot"):
                return await self._snap(client)
            if cmd in ("/stream", "/video"):
                return CommandResult(text="Telegram canlı stream desteklemiyor; lokal MJPEG: /camera/video")
            if cmd in ("/pt", "/track"):
                return CommandResult(text=await self._pan_tilt(client, args))
            if cmd == "/pan":
                return CommandResult(text=await self._pan_tilt(client, args, single_axis="pan"))
            if cmd == "/tilt":
                return CommandResult(text=await self._pan_tilt(client, args, single_axis="tilt"))
            if cmd in ("/neofill", "/fill"):
                return CommandResult(text=await self._neofill(client, args))
            if cmd in ("/neoclear", "/clear"):
                return CommandResult(text=await self._post_ok(client, "/neopixel/clear", "NeoPixel cleared"))
            if cmd in ("/say", "/tts"):
                return CommandResult(text=await self._say(client, args))
            return None
        except Exception as exc:
            return CommandResult(text=f"Hata: {exc}")

    def _help(self) -> str:
        return (
            "Komutlar:\n"
            "/status - modüllerin sağlık kontrolü\n"
            "/snap - kamera fotoğraf gönder\n"
            "/stream - stream bilgisi\n"
            "/pt <pan> <tilt> - pan/tilt derece\n"
            "/pan <deg> - sadece pan\n"
            "/tilt <deg> - sadece tilt\n"
            "/neofill r g b - tüm LED renk\n"
            "/neoclear - LED temizle\n"
            "/say <metin> - TTS oynat"
        )

    async def _status(self, client: httpx.AsyncClient) -> str:
        url = f"{self._base}/health"
        try:
            resp = await client.get(url, timeout=self._timeout)
            if resp.status_code != 200:
                return f"Status error: {resp.status_code}"
            data = resp.json()
            mods = data if isinstance(data, dict) else {}
            summary = []
            for name, info in mods.items():
                if name == "ok":
                    continue
                ok = info.get("ok", False) if isinstance(info, dict) else False
                summary.append(f"{name}:{'ok' if ok else 'fail'}")
            return "Durum " + ("ok" if mods.get("ok", False) else "fail") + " " + ", ".join(summary)
        except Exception as exc:
            return f"Status hata: {exc}"

    async def _pan_tilt(self, client: httpx.AsyncClient, args: list[str], single_axis: str | None = None) -> str:
        pan: float | None = None
        tilt: float | None = None
        try:
            if single_axis == "pan":
                pan = float(args[0]) if args else None
                tilt = 0.0
            elif single_axis == "tilt":
                tilt = float(args[0]) if args else None
                pan = 0.0
            else:
                pan = float(args[0]) if len(args) >= 1 else None
                tilt = float(args[1]) if len(args) >= 2 else None
        except Exception:
            return "Kullanım: /pt <pan> <tilt> (derece)"
        if pan is None or tilt is None:
            return "Kullanım: /pt <pan> <tilt>"
        params = {"head_pan": pan, "head_tilt": tilt}
        url = f"{self._base}/vision/track"
        ok = await self._post_bool(client, url, params=params)
        return "Pan/tilt ok" if ok else "Pan/tilt başarısız"

    async def _neofill(self, client: httpx.AsyncClient, args: list[str]) -> str:
        try:
            r, g, b = [int(x) for x in args[:3]]
        except Exception:
            return "Kullanım: /neofill <r> <g> <b>"
        url = f"{self._base}/neopixel/fill"
        params = {"r_": r, "g": g, "b": b}
        ok = await self._post_bool(client, url, params=params)
        return "NeoPixel set" if ok else "NeoPixel hata"

    async def _say(self, client: httpx.AsyncClient, args: list[str]) -> str:
        text = " ".join(args).strip()
        if not text:
            return "Kullanım: /say <metin>"
        url = f"{self._base}/speak/say"
        try:
            resp = await client.post(url, json={"text": text}, timeout=max(self._timeout, 15.0))
        except Exception as exc:
            return f"TTS istek hatası: {exc!r}"
        if resp.status_code != 200:
            return f"TTS http {resp.status_code}"
        data = None
        try:
            if resp.headers.get("content-type", "").startswith("application/json"):
                data = resp.json()
        except Exception:
            data = None
        if isinstance(data, dict):
            if data.get("ok"):
                return "TTS oynatılıyor"
            err = data.get("error") or data
            return f"TTS hata: {err}"
        return "TTS oynatılıyor"

    async def _snap(self, client: httpx.AsyncClient) -> CommandResult:
        url = f"{self._base}/camera/snap"
        try:
            resp = await client.get(url, timeout=self._timeout)
            if resp.status_code != 200:
                return CommandResult(text=f"Snapshot hata: {resp.status_code}")
            return CommandResult(photo=resp.content)
        except Exception as exc:
            return CommandResult(text=f"Snapshot hata: {exc}")

    async def _post_ok(self, client: httpx.AsyncClient, path: str, success_msg: str) -> str:
        url = f"{self._base}{path}"
        ok = await self._post_bool(client, url)
        return success_msg if ok else f"Hata: {path}"

    async def _post_bool(self, client: httpx.AsyncClient, url: str, json: dict | None = None, params: dict | None = None) -> bool:
        try:
            resp = await client.post(url, json=json, params=params, timeout=self._timeout)
            if resp.status_code != 200:
                return False
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None
            if isinstance(data, dict) and "ok" in data:
                return bool(data.get("ok", False))
            return True
        except Exception:
            return False
