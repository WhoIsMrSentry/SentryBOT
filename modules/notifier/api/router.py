from __future__ import annotations
from typing import Dict, Any
from fastapi import APIRouter

from ..services.senders import send_telegram, send_discord


def get_router(cfg: Dict[str, Any]) -> APIRouter:
    r = APIRouter(prefix="/notify", tags=["notifier"])

    @r.get("/healthz")
    def healthz():
        return {"ok": True}

    @r.post("/telegram")
    def tele(body: Dict[str, Any]):
        token = cfg.get("telegram", {}).get("bot_token", "")
        chat_id = cfg.get("telegram", {}).get("chat_id", "")
        ok = bool(token and chat_id) and send_telegram(token, chat_id, str(body.get("text", "")))
        return {"ok": ok}

    @r.post("/discord")
    def disc(body: Dict[str, Any]):
        webhook = cfg.get("discord", {}).get("webhook", "")
        ok = bool(webhook) and send_discord(webhook, str(body.get("text", "")))
        return {"ok": ok}

    @r.post("/test")
    def test():
        msg = "SentryBOT notifier test"
        res = {"telegram": False, "discord": False}
        t = cfg.get("telegram", {})
        d = cfg.get("discord", {})
        if t.get("bot_token") and t.get("chat_id"):
            res["telegram"] = send_telegram(t["bot_token"], t["chat_id"], msg)
        if d.get("webhook"):
            res["discord"] = send_discord(d["webhook"], msg)
        return {"ok": any(res.values()), "results": res}

    return r
