from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, time
from typing import Iterable, Optional

import httpx

from .command_router import CommandRouter, CommandResult


logger = logging.getLogger("notifier.telegram")


@dataclass
class QuietHours:
    enabled: bool
    start: time
    end: time

    def is_quiet_now(self, now: Optional[datetime] = None) -> bool:
        if not self.enabled:
            return False
        current = (now or datetime.now()).time()
        # Quiet hours may wrap past midnight (e.g., 23:00-08:00)
        if self.start <= self.end:
            return self.start <= current < self.end
        return current >= self.start or current < self.end


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(int(hour), int(minute))


class TelegramBot:
    def __init__(
        self,
        bot_token: str,
        default_chat_id: str,
        *,
        allowed_user_ids: Iterable[int] | None = None,
        poll_interval: float = 2.5,
        quiet_hours: QuietHours | None = None,
        command_router: CommandRouter | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._default_chat_id = default_chat_id
        self._allowed_user_ids = set(allowed_user_ids or [])
        self._poll_interval = poll_interval
        self._quiet_hours = quiet_hours or QuietHours(False, time(0, 0), time(0, 0))
        self._commands = command_router

        self._offset = 0
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._task:
            return
        self._client = httpx.AsyncClient()
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("telegram polling started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        logger.info("telegram polling stopped")

    async def send(self, text: str, *, chat_id: str | None = None) -> bool:
        if not self._client:
            self._client = httpx.AsyncClient()
        target_chat = chat_id or self._default_chat_id
        if not target_chat:
            return False
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            res = await self._client.post(
                url,
                json={"chat_id": target_chat, "text": text},
                timeout=10.0,
            )
            return res.status_code == 200
        except Exception:
            return False

    async def send_photo(self, photo: bytes, *, chat_id: str | None = None, caption: str | None = None) -> bool:
        if not self._client:
            self._client = httpx.AsyncClient()
        target_chat = chat_id or self._default_chat_id
        if not target_chat:
            return False
        url = f"https://api.telegram.org/bot{self._bot_token}/sendPhoto"
        try:
            files = {"photo": ("snap.jpg", photo, "image/jpeg")}
            data = {"chat_id": target_chat}
            if caption:
                data["caption"] = caption
            res = await self._client.post(url, data=data, files=files, timeout=20.0)
            return res.status_code == 200
        except Exception:
            return False

    async def _poll_loop(self) -> None:
        assert self._client is not None
        base_url = f"https://api.telegram.org/bot{self._bot_token}"
        while True:
            try:
                res = await self._client.get(
                    f"{base_url}/getUpdates",
                    params={"offset": self._offset + 1, "timeout": 20},
                    timeout=25.0,
                )
                data = res.json()
                if not data.get("ok"):
                    logger.warning("getUpdates not ok: %s", data)
                    await asyncio.sleep(self._poll_interval)
                    continue
                items = data.get("result", [])
                if items:
                    logger.info("received %s update(s)", len(items))
                for update in items:
                    self._offset = max(self._offset, int(update.get("update_id", 0)))
                    await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("poll loop error")
                # Cooldown on any error to avoid busy looping
                await asyncio.sleep(self._poll_interval)

    async def _handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        user_id = int(message.get("from", {}).get("id", 0))
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = str(message.get("text", ""))

        if self._allowed_user_ids and user_id not in self._allowed_user_ids:
            logger.info("skip unauthorized user %s", user_id)
            return

        if self._quiet_hours.is_quiet_now():
            await self.send("Quiet hours are active.", chat_id=chat_id)
            logger.info("quiet hours active; informed chat %s", chat_id)
            return

        lower = text.lower().strip()

        # Core bot commands
        if lower.startswith("/start"):
            await self.send("SentryBOT notifier aktif.", chat_id=chat_id)
            logger.info("/start handled for chat %s", chat_id)
            return
        if lower.startswith("/ping"):
            await self.send("pong", chat_id=chat_id)
            logger.info("/ping handled for chat %s", chat_id)
            return

        # Extended commands routed to services
        if self._commands:
            result = await self._commands.handle(self._client, text)
            if isinstance(result, CommandResult):
                sent = False
                if result.photo:
                    sent = await self.send_photo(result.photo, chat_id=chat_id, caption=result.text or None)
                elif result.text:
                    sent = await self.send(result.text, chat_id=chat_id)
                if sent:
                    logger.info("command handled via router for chat %s", chat_id)
                    return

        if lower.startswith("/help"):
            await self.send("Komutlar: /ping, /help", chat_id=chat_id)
            logger.info("/help handled for chat %s", chat_id)
            return

        await self.send(f"Aldım: {text}", chat_id=chat_id)
        logger.info("echoed message for chat %s", chat_id)


def build_telegram_bot(cfg: dict) -> TelegramBot | None:
    telegram_cfg = cfg.get("telegram", {})
    token = telegram_cfg.get("bot_token", "")
    chat_id = telegram_cfg.get("chat_id", "")
    if not token:
        return None

    quiet_cfg = cfg.get("quiet_hours", {})
    quiet = QuietHours(
        bool(quiet_cfg.get("enabled", False)),
        _parse_time(quiet_cfg.get("start", "23:00")),
        _parse_time(quiet_cfg.get("end", "08:00")),
    )
    poll_cfg = telegram_cfg.get("polling", {})
    allowed = telegram_cfg.get("allowed_user_ids") or []

    gw_cfg = cfg.get("gateway", {})
    router = CommandRouter(
        gw_cfg.get("base_url", "http://127.0.0.1:8080"),
        timeout=float(gw_cfg.get("timeout_sec", 4.0)),
    )

    return TelegramBot(
        token,
        chat_id,
        allowed_user_ids=[int(u) for u in allowed],
        poll_interval=float(poll_cfg.get("interval_sec", 2.5)),
        quiet_hours=quiet,
        command_router=router,
    )
