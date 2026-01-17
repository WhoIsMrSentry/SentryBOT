from __future__ import annotations
from datetime import datetime, time
from typing import Dict, Any
from fastapi import APIRouter

from ..services.senders import send_telegram, send_discord
from ..services.telegram_bot import TelegramBot
from ..services.whatsapp_web import WhatsAppWebSender


def _quiet_hours_active(cfg: Dict[str, Any]) -> bool:
    quiet_cfg = cfg.get("quiet_hours", {})
    if not quiet_cfg.get("enabled", False):
        return False
    def _parse(value: str) -> time:
        h, m = value.split(":", maxsplit=1)
        return time(int(h), int(m))
    start = _parse(quiet_cfg.get("start", "23:00"))
    end = _parse(quiet_cfg.get("end", "08:00"))
    now = datetime.now().time()
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def get_router(
    cfg: Dict[str, Any],
    bot: TelegramBot | None = None,
    whatsapp_web: WhatsAppWebSender | None = None,
) -> APIRouter:
    r = APIRouter(prefix="/notify", tags=["notifier"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.post("/telegram")
    async def tele(body: Dict[str, Any]):
        if _quiet_hours_active(cfg):
            return {"ok": False, "reason": "quiet_hours"}

        token = cfg.get("telegram", {}).get("bot_token", "")
        chat_id_default = cfg.get("telegram", {}).get("chat_id", "")
        target_chat = str(body.get("chat_id") or chat_id_default)
        text = str(body.get("text", ""))

        ok = False
        if bot:
            ok = await bot.send(text, chat_id=target_chat)
        elif token and target_chat:
            ok = send_telegram(token, target_chat, text)
        return {"ok": ok}

    @r.post("/discord")
    def disc(body: Dict[str, Any]):
        webhook = cfg.get("discord", {}).get("webhook", "")
        ok = bool(webhook) and send_discord(webhook, str(body.get("text", "")))
        return {"ok": ok}

    @r.post("/test")
    async def test():
        msg = "SentryBOT notifier test"
        res = {"telegram": False, "discord": False, "whatsapp": False}
        t = cfg.get("telegram", {})
        d = cfg.get("discord", {})
        if t.get("bot_token") and t.get("chat_id"):
            if bot:
                res["telegram"] = await bot.send(msg)
            else:
                res["telegram"] = send_telegram(t["bot_token"], t["chat_id"], msg)
        if d.get("webhook"):
            res["discord"] = send_discord(d["webhook"], msg)
        if whatsapp_web:
            res["whatsapp"] = await whatsapp_web.send_text(msg)
        return {"ok": any(res.values()), "results": res}

    @r.post("/whatsapp")
    async def whatsapp_send(body: Dict[str, Any]):
        if _quiet_hours_active(cfg):
            return {"ok": False, "reason": "quiet_hours"}
        if not whatsapp_web:
            return {"ok": False, "reason": "disabled"}
        text = str(body.get("text", "")).strip()
        if not text:
            return {"ok": False, "reason": "empty_text"}
        target = str(body.get("to") or body.get("recipient") or "").strip() or None
        delay_override_sec = body.get("delay_sec")
        try:
            delay_value = int(delay_override_sec) if delay_override_sec is not None else None
        except Exception:
            delay_value = None
        ok = await whatsapp_web.send_text(text, to=target, delay_override_sec=delay_value)
        return {"ok": ok}

    @r.post("/start")
    async def start_bot():
        if bot:
            await bot.start()
            return {"ok": True, "status": "polling_started"}
        return {"ok": False, "reason": "no_bot_configured"}

    @r.post("/stop")
    async def stop_bot():
        if bot:
            await bot.stop()
            return {"ok": True, "status": "polling_stopped"}
        return {"ok": False, "reason": "no_bot_configured"}

    return r
