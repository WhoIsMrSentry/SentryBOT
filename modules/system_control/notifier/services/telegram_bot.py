from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime, time
import logging
from typing import Any, Iterable, Mapping, Optional

import httpx

from modules.common.config_loader import redact_secrets
from modules.common.time_utils import is_time_in_window, parse_hhmm

from .command_router import CommandResult, CommandRouter

logger = logging.getLogger("notifier.telegram")


def _to_hhmm(value: time | tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, tuple):
        return (int(value[0]), int(value[1]))
    return (value.hour, value.minute)


def _parse_hhmm_or_default(value: Any, fallback: tuple[int, int]) -> time:
    parsed = parse_hhmm(value)
    if parsed is None:
        logger.warning("invalid quiet_hours time %r; falling back to %02d:%02d", value, fallback[0], fallback[1])
        return time(fallback[0], fallback[1])
    return time(parsed[0], parsed[1])


@dataclass
class QuietHours:
    enabled: bool
    start: time
    end: time

    @classmethod
    def from_config(cls, quiet_cfg: Mapping[str, Any] | None) -> QuietHours:
        cfg = quiet_cfg or {}
        return cls(
            enabled=bool(cfg.get("enabled", False)),
            start=_parse_hhmm_or_default(cfg.get("start", "23:00"), (23, 0)),
            end=_parse_hhmm_or_default(cfg.get("end", "08:00"), (8, 0)),
        )

    def is_quiet_now(self, now: Optional[datetime] = None) -> bool:
        if not self.enabled:
            return False
        current = now or datetime.now()
        return is_time_in_window(
            (current.hour, current.minute),
            _to_hhmm(self.start),
            _to_hhmm(self.end),
        )


class TelegramBot:
    def __init__(
        self,
        bot_token: str,
        default_chat_id: str,
        *,
        allowed_user_ids: Iterable[int] | None = None,
        allow_public: bool = False,
        poll_interval: float = 2.5,
        quiet_hours: QuietHours | None = None,
        command_router: CommandRouter | None = None,
    ) -> None:
        self._bot_token = bot_token.strip('"').strip("'")
        self._default_chat_id = default_chat_id
        self._allowed_user_ids = set(allowed_user_ids or [])
        self._allow_public = bool(allow_public)
        self._poll_interval = poll_interval
        self._quiet_hours = quiet_hours or QuietHours(False, time(0, 0), time(0, 0))
        self._commands = command_router

        self._offset = 0
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None

    def _is_authorized(self, user_id: int) -> bool:
        if self._allowed_user_ids:
            return user_id in self._allowed_user_ids
        return self._allow_public

    def _ensure_client(self) -> httpx.AsyncClient:
        if not self._client:
            self._client = httpx.AsyncClient()
        return self._client

    def _safe_error(self, exc: Exception) -> str:
        raw = str(exc)
        if self._bot_token:
            raw = raw.replace(self._bot_token, "***")
        return redact_secrets(raw)

    async def start(self) -> None:
        if self._task:
            return
        self._ensure_client()
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
        target_chat = chat_id or self._default_chat_id
        if not self._bot_token or not target_chat:
            return False
        client = self._ensure_client()
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            res = await client.post(
                url,
                json={"chat_id": target_chat, "text": text},
                timeout=10.0,
            )
            if res.status_code != 200:
                logger.warning("telegram sendMessage status=%s chat=%s", res.status_code, target_chat)
                return False
            return True
        except Exception as exc:
            logger.warning("telegram sendMessage failed: %s", self._safe_error(exc))
            return False

    async def send_photo(self, photo: bytes, *, chat_id: str | None = None, caption: str | None = None) -> bool:
        target_chat = chat_id or self._default_chat_id
        if not self._bot_token or not target_chat or not photo:
            return False
        client = self._ensure_client()
        url = f"https://api.telegram.org/bot{self._bot_token}/sendPhoto"
        try:
            files = {"photo": ("snap.jpg", photo, "image/jpeg")}
            data = {"chat_id": target_chat}
            if caption:
                data["caption"] = caption
            res = await client.post(url, data=data, files=files, timeout=20.0)
            if res.status_code != 200:
                logger.warning("telegram sendPhoto status=%s chat=%s", res.status_code, target_chat)
                return False
            return True
        except Exception as exc:
            logger.warning("telegram sendPhoto failed: %s", self._safe_error(exc))
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
                await asyncio.sleep(self._poll_interval)

    async def _handle_update(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        try:
            user_id = int(message.get("from", {}).get("id", 0))
        except (TypeError, ValueError):
            user_id = 0
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = str(message.get("text", ""))

        if not self._is_authorized(user_id):
            logger.warning("skip unauthorized user %s", user_id)
            return

        if self._quiet_hours.is_quiet_now():
            logger.info("quiet hours active; ignoring update from chat %s", chat_id)
            return

        lower = text.lower().strip()

        if lower.startswith("/start"):
            await self.send("SentryBOT notifier aktif.", chat_id=chat_id)
            logger.info("/start handled for chat %s", chat_id)
            return
        if lower.startswith("/ping"):
            await self.send("pong", chat_id=chat_id)
            logger.info("/ping handled for chat %s", chat_id)
            return

        if self._commands:
            result = await self._commands.handle(
                self._ensure_client(),
                text,
                user_id=user_id,
                chat_id=chat_id,
            )
            if isinstance(result, CommandResult):
                if result.photo:
                    await self.send_photo(
                        result.photo,
                        chat_id=chat_id,
                        caption=result.photo_caption or result.text or None,
                    )
                    logger.info("photo command handled via router for chat %s", chat_id)
                    return
                if result.text:
                    await self.send(result.text, chat_id=chat_id)
                    logger.info("command handled via router for chat %s", chat_id)
                    return

        if lower.startswith("/help"):
            help_text = self._commands.get_help_text() if self._commands else "Komutlar: /ping, /help"
            await self.send(help_text, chat_id=chat_id)
            logger.info("/help handled for chat %s", chat_id)
            return

        await self.send(f"Aldım: {text}", chat_id=chat_id)
        logger.info("echoed message for chat %s", chat_id)


def build_telegram_bot(cfg: dict) -> TelegramBot | None:
    telegram_cfg = cfg.get("telegram", {})
    token = str(telegram_cfg.get("bot_token", "") or "")
    chat_id = str(telegram_cfg.get("chat_id", "") or "")
    if not token:
        return None

    quiet = QuietHours.from_config(cfg.get("quiet_hours", {}))
    poll_cfg = telegram_cfg.get("polling", {})
    raw_allowed = telegram_cfg.get("allowed_user_ids") or []
    allowed_ids: list[int] = []
    for item in raw_allowed:
        try:
            allowed_ids.append(int(item))
        except (TypeError, ValueError):
            logger.warning("ignoring non-integer allowed_user_id: %r", item)

    gw_cfg = cfg.get("gateway", {})
    router = CommandRouter(
        gw_cfg.get("base_url", "http://127.0.0.1:8080"),
        timeout=float(gw_cfg.get("timeout_sec", 4.0)),
    )

    return TelegramBot(
        token,
        chat_id,
        allowed_user_ids=allowed_ids,
        allow_public=bool(telegram_cfg.get("allow_public", False)),
        poll_interval=float(poll_cfg.get("interval_sec", 2.5)),
        quiet_hours=quiet,
        command_router=router,
    )
