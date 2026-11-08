from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from modules.common.config_loader import redact_secrets

logger = logging.getLogger("notifier.senders")

_CLIENT_LOCK = threading.Lock()
_SYNC_CLIENT: Optional[Any] = None


def _get_client() -> Any:
    import httpx  # type: ignore

    with _CLIENT_LOCK:
        global _SYNC_CLIENT
        if _SYNC_CLIENT is None or getattr(_SYNC_CLIENT, "is_closed", False):
            _SYNC_CLIENT = httpx.Client(timeout=5.0)
        return _SYNC_CLIENT


def close_senders() -> None:
    """Close shared synchronous HTTP client if open."""
    with _CLIENT_LOCK:
        global _SYNC_CLIENT
        if _SYNC_CLIENT is not None:
            try:
                _SYNC_CLIENT.close()
            except Exception as exc:
                logger.warning("closing notifier sender client failed: %s", exc)
            _SYNC_CLIENT = None


def send_telegram(bot_token: str, chat_id: str, text: str) -> bool:
    if not bot_token or not chat_id:
        return False
    try:
        client = _get_client()
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = client.post(url, json={"chat_id": chat_id, "text": text}, timeout=5.0)
        if r.status_code != 200:
            logger.warning("telegram sendMessage status=%s", r.status_code)
            return False
        return True
    except Exception as exc:
        safe_msg = redact_secrets(str(exc).replace(bot_token, "***"))
        logger.warning("telegram sendMessage failed: %s", safe_msg)
        return False


def send_discord(webhook: str, content: str) -> bool:
    if not webhook:
        return False
    try:
        client = _get_client()
        r = client.post(webhook, json={"content": content}, timeout=5.0)
        if r.status_code not in (200, 204):
            logger.warning("discord webhook status=%s", r.status_code)
            return False
        return True
    except Exception as exc:
        logger.warning("discord webhook failed: %s", redact_secrets(exc))
        return False
