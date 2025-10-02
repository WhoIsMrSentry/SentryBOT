from __future__ import annotations
from typing import Optional


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    try:
        import httpx  # type: ignore
    except Exception:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        with httpx.Client() as c:
            r = c.post(url, json={"chat_id": chat_id, "text": text}, timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


def send_discord(webhook: str, content: str) -> bool:
    try:
        import httpx  # type: ignore
    except Exception:
        return False
    try:
        with httpx.Client() as c:
            r = c.post(webhook, json={"content": content}, timeout=5.0)
        return r.status_code in (200, 204)
    except Exception:
        return False
