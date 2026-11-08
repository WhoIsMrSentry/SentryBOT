from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

from modules.common.bind_host import apply_bind_host
from modules.common.config_loader import load_dotenv, load_module_config

logger = logging.getLogger("notifier.config")

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "config.yml"
_DEFAULT_DOTENV_PATH = Path(__file__).parent / ".env"


def _str_to_bool(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "on"}


def _parse_allowed_user_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for item in raw.split(","):
        token = item.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            logger.warning("ignoring invalid user id %r in NOTIFIER_ALLOWED_USER_IDS", token)
    return ids


def _apply_env(cfg: Dict[str, Any]) -> Dict[str, Any]:
    bot_token = os.getenv("NOTIFIER_BOT_TOKEN")
    chat_id = os.getenv("NOTIFIER_CHAT_ID")
    discord_webhook = os.getenv("NOTIFIER_DISCORD_WEBHOOK")
    allowed = os.getenv("NOTIFIER_ALLOWED_USER_IDS")
    polling = os.getenv("NOTIFIER_POLLING_ENABLED")
    allow_public = os.getenv("NOTIFIER_ALLOW_PUBLIC")
    gateway = os.getenv("NOTIFIER_GATEWAY_BASE_URL")

    if any(val is not None for val in (bot_token, chat_id, allowed, polling, allow_public)):
        cfg.setdefault("telegram", {})
    if bot_token:
        cfg["telegram"]["bot_token"] = bot_token
    if chat_id:
        cfg["telegram"]["chat_id"] = chat_id
    if allowed is not None:
        cfg["telegram"]["allowed_user_ids"] = _parse_allowed_user_ids(allowed)
    if polling is not None:
        cfg.setdefault("telegram", {}).setdefault("polling", {})["enabled"] = _str_to_bool(polling)
    if allow_public is not None:
        cfg.setdefault("telegram", {})["allow_public"] = _str_to_bool(allow_public)

    if discord_webhook:
        cfg.setdefault("discord", {})["webhook"] = discord_webhook

    if gateway:
        cfg.setdefault("gateway", {})["base_url"] = gateway

    return cfg


def load_config(path: str | None = None) -> Dict[str, Any]:
    load_dotenv(_DEFAULT_DOTENV_PATH)
    cfg = load_module_config(_DEFAULT_CFG_PATH, path)
    cfg = _apply_env(cfg)
    return apply_bind_host(cfg, "NOTIFIER_HOST")
