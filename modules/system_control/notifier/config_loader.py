from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict
import yaml

_DEFAULT_CFG_PATH = Path(__file__).parent / "config" / "config.yml"
_DEFAULT_DOTENV_PATH = Path(__file__).parent / ".env"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip()


def _str_to_bool(v: str) -> bool:
    return str(v).lower() in {"1", "true", "yes", "on"}


def _apply_env(cfg: Dict[str, Any]) -> Dict[str, Any]:
    bot_token = os.getenv("NOTIFIER_BOT_TOKEN")
    chat_id = os.getenv("NOTIFIER_CHAT_ID")
    discord_webhook = os.getenv("NOTIFIER_DISCORD_WEBHOOK")
    allowed = os.getenv("NOTIFIER_ALLOWED_USER_IDS")
    polling = os.getenv("NOTIFIER_POLLING_ENABLED")
    gateway = os.getenv("NOTIFIER_GATEWAY_BASE_URL")

    if bot_token or chat_id or allowed or polling:
        cfg.setdefault("telegram", {})
    if bot_token:
        cfg["telegram"]["bot_token"] = bot_token
    if chat_id:
        cfg["telegram"]["chat_id"] = chat_id
    if allowed:
        cfg["telegram"]["allowed_user_ids"] = [int(x) for x in allowed.split(",") if x.strip()]
    if polling is not None:
        cfg.setdefault("telegram", {}).setdefault("polling", {})["enabled"] = _str_to_bool(polling)

    if discord_webhook:
        cfg.setdefault("discord", {})["webhook"] = discord_webhook

    if gateway:
        cfg.setdefault("gateway", {})["base_url"] = gateway

    return cfg


def load_config(path: str | None = None) -> Dict[str, Any]:
    # allow .env to set env vars without extra dependencies
    _load_dotenv(_DEFAULT_DOTENV_PATH)

    p = Path(path) if path else _DEFAULT_CFG_PATH
    if not p.exists():
        p = _DEFAULT_CFG_PATH
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    return _apply_env(cfg)
