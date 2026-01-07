from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("notifier.whatsapp_web")


class WhatsAppWebSender:
    def __init__(
        self,
        recipient: str,
        *,
        wait_time_sec: int = 15,
        tab_close: bool = True,
        close_time_sec: int = 5,
        send_mode: str = "instant",
        schedule_delay_sec: int = 75,
    ) -> None:
        self._recipient = recipient.strip()
        self._wait_time = max(wait_time_sec, 1)
        self._tab_close = tab_close
        self._close_time = max(close_time_sec, 1)
        self._send_mode = send_mode if send_mode in ("instant", "schedule") else "instant"
        self._schedule_delay = max(schedule_delay_sec, 60)

    async def send_text(self, text: str, *, to: str | None = None, delay_override_sec: int | None = None) -> bool:
        message = text.strip()
        target = (to or self._recipient).strip()
        if not message or not target:
            return False
        delay = delay_override_sec if delay_override_sec is not None else None
        if delay is None and self._send_mode == "schedule":
            delay = self._schedule_delay
        return await asyncio.to_thread(self._send_blocking, target, message, delay)

    def _send_blocking(self, phone_number: str, message: str, delay_sec: int | None) -> bool:
        try:
            import pywhatkit
        except Exception:
            logger.error("pywhatkit bulunamadı. `pip install pywhatkit` çalıştırın.")
            return False
        try:
            if delay_sec is None:
                pywhatkit.sendwhatmsg_instantly(
                    phone_number,
                    message,
                    wait_time=self._wait_time,
                    tab_close=self._tab_close,
                    close_time=self._close_time,
                )
                return True
            fire_at = datetime.now() + timedelta(seconds=max(delay_sec, 60))
            pywhatkit.sendwhatmsg(
                phone_number,
                message,
                fire_at.hour,
                fire_at.minute,
                wait_time=self._wait_time,
                tab_close=self._tab_close,
                close_time=self._close_time,
            )
            return True
        except Exception:
            logger.exception("WhatsApp Web mesajı gönderilemedi")
            return False


def build_whatsapp_web_sender(cfg: dict) -> WhatsAppWebSender | None:
    web_cfg = cfg.get("whatsapp_web", {})
    if not web_cfg.get("enabled", False):
        return None
    recipient = str(web_cfg.get("recipient", "")).strip()
    if not recipient:
        logger.warning("whatsapp_web etkin ancak recipient boş")
        return None
    return WhatsAppWebSender(
        recipient=recipient,
        wait_time_sec=int(web_cfg.get("wait_time_sec", 15)),
        tab_close=bool(web_cfg.get("tab_close", True)),
        close_time_sec=int(web_cfg.get("close_time_sec", 5)),
        send_mode=str(web_cfg.get("send_mode", "instant")),
        schedule_delay_sec=int(web_cfg.get("schedule_delay_sec", 75)),
    )
