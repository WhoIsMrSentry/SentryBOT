from __future__ import annotations

import threading
import time
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool

from ..services.senders import send_discord, send_telegram
from ..services.telegram_bot import QuietHours, TelegramBot

_MAX_DEBOUNCE_ENTRIES = 256


class NotifySendPayload(BaseModel):
    text: Optional[str] = None
    message: Optional[str] = None
    title: Optional[str] = None
    priority: Literal["normal", "critical"] = "normal"
    channels: Optional[list[str]] = Field(default=None)
    chat_id: Optional[str] = None

    @model_validator(mode="after")
    def _ensure_non_empty_text(self) -> NotifySendPayload:
        resolved = (self.text if self.text is not None else self.message or "").strip()
        if not resolved:
            raise ValueError("text or message must be non-empty")
        self.text = resolved
        return self


def _quiet_hours_active(cfg: Dict[str, Any]) -> bool:
    return QuietHours.from_config((cfg or {}).get("quiet_hours", {})).is_quiet_now()


async def _dispatch_telegram(
    cfg: Dict[str, Any],
    bot: TelegramBot | None,
    text: str,
    *,
    chat_id: str | None = None,
) -> bool:
    t = cfg.get("telegram", {})
    token = str(t.get("bot_token", "") or "")
    target_chat = str(chat_id or t.get("chat_id", "") or "")
    if bot:
        return await bot.send(text, chat_id=target_chat or None)
    if token and target_chat:
        return await run_in_threadpool(send_telegram, token, target_chat, text)
    return False


async def _dispatch_discord(cfg: Dict[str, Any], text: str) -> bool:
    webhook = str(cfg.get("discord", {}).get("webhook", "") or "")
    if not webhook:
        return False
    return await run_in_threadpool(send_discord, webhook, text)


def get_router(
    cfg: Dict[str, Any],
    bot: TelegramBot | None = None,
) -> APIRouter:
    r = APIRouter(prefix="/notify", tags=["notifier"])
    cooldown_sec = max(0.0, float((cfg or {}).get("send", {}).get("cooldown_sec", 10.0)))
    debounce_lock = threading.Lock()
    recent_sent: dict[tuple[str, str], float] = {}

    def _is_debounced(priority: str, content: str) -> bool:
        if cooldown_sec <= 0.0:
            return False
        now = time.monotonic()
        key = (priority, content)
        with debounce_lock:
            last = recent_sent.get(key)
            if last is not None and (now - last) < cooldown_sec:
                return True
        return False

    def _mark_sent(priority: str, content: str) -> None:
        if cooldown_sec <= 0.0:
            return
        now = time.monotonic()
        with debounce_lock:
            if len(recent_sent) >= _MAX_DEBOUNCE_ENTRIES:
                cutoff = now - cooldown_sec
                expired = [k for k, ts in recent_sent.items() if ts <= cutoff]
                for k in expired:
                    recent_sent.pop(k, None)
                if len(recent_sent) >= _MAX_DEBOUNCE_ENTRIES:
                    recent_sent.clear()
            recent_sent[(priority, content)] = now

    @r.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {"ok": True}

    @r.post("/telegram")
    async def tele(body: Dict[str, Any]) -> Dict[str, Any]:
        if _quiet_hours_active(cfg):
            return {"ok": False, "reason": "quiet_hours"}

        text = str(body.get("text", ""))
        chat_id = body.get("chat_id")
        ok = await _dispatch_telegram(cfg, bot, text, chat_id=str(chat_id) if chat_id else None)
        return {"ok": ok}

    @r.post("/discord")
    async def disc(body: Dict[str, Any]) -> Dict[str, Any]:
        if _quiet_hours_active(cfg):
            return {"ok": False, "reason": "quiet_hours"}

        text = str(body.get("text", ""))
        ok = await _dispatch_discord(cfg, text)
        return {"ok": ok}

    @r.post("/send")
    async def send(payload: NotifySendPayload) -> Dict[str, Any]:
        assert payload.text is not None
        if _quiet_hours_active(cfg) and payload.priority != "critical":
            return {"ok": False, "reason": "quiet_hours", "priority": payload.priority, "results": {}}

        clean_title = payload.title.strip() if payload.title else ""
        if clean_title:
            formatted = f"[{clean_title}] {payload.text}"
        elif payload.priority == "critical":
            formatted = f"[CRITICAL] {payload.text}"
        else:
            formatted = payload.text

        if _is_debounced(payload.priority, formatted):
            return {
                "ok": False,
                "reason": "debounced",
                "priority": payload.priority,
                "cooldown_sec": cooldown_sec,
                "results": {},
            }

        requested = (
            {c.strip().lower() for c in payload.channels if c.strip()}
            if payload.channels
            else {"telegram", "discord"}
        )
        results: Dict[str, bool] = {}

        t = cfg.get("telegram", {})
        if "telegram" in requested and (bot or (t.get("bot_token") and (payload.chat_id or t.get("chat_id")))):
            results["telegram"] = await _dispatch_telegram(cfg, bot, formatted, chat_id=payload.chat_id)

        d = cfg.get("discord", {})
        if "discord" in requested and d.get("webhook"):
            results["discord"] = await _dispatch_discord(cfg, formatted)

        ok = any(results.values())
        if ok:
            _mark_sent(payload.priority, formatted)
        return {"ok": ok, "priority": payload.priority, "results": results}

    @r.post("/test")
    async def test() -> Dict[str, Any]:
        msg = "SentryBOT notifier test"
        res = {"telegram": False, "discord": False}
        t = cfg.get("telegram", {})
        d = cfg.get("discord", {})
        if t.get("bot_token") and t.get("chat_id"):
            res["telegram"] = await _dispatch_telegram(cfg, bot, msg)
        if d.get("webhook"):
            res["discord"] = await _dispatch_discord(cfg, msg)
        return {"ok": any(res.values()), "results": res}

    @r.post("/start")
    async def start_bot() -> Dict[str, Any]:
        if bot:
            await bot.start()
            return {"ok": True, "status": "polling_started"}
        return {"ok": False, "reason": "no_bot_configured"}

    @r.post("/stop")
    async def stop_bot() -> Dict[str, Any]:
        if bot:
            await bot.stop()
            return {"ok": True, "status": "polling_stopped"}
        return {"ok": False, "reason": "no_bot_configured"}

    return r
