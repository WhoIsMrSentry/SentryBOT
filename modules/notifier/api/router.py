from __future__ import annotations
from datetime import datetime, time
from typing import Dict, Any
from fastapi import APIRouter

from ..services.senders import send_telegram, send_discord
from ..services.telegram_bot import TelegramBot


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


def get_router(cfg: Dict[str, Any], bot: TelegramBot | None = None) -> APIRouter:
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
        res = {"telegram": False, "discord": False}
        t = cfg.get("telegram", {})
        d = cfg.get("discord", {})
        if t.get("bot_token") and t.get("chat_id"):
            if bot:
                res["telegram"] = await bot.send(msg)
            else:
                res["telegram"] = send_telegram(t["bot_token"], t["chat_id"], msg)
        if d.get("webhook"):
            res["discord"] = send_discord(d["webhook"], msg)
        return {"ok": any(res.values()), "results": res}

    return r
