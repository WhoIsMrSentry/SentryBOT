from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

try:
    import httpx  # type: ignore
except Exception:
    httpx = None

logger = logging.getLogger("vlm_bridge.llm")

_DEFAULT_CHAT_ENDPOINT = "http://localhost:8080/ollama/chat"
_DEFAULT_GENERATE_ENDPOINT = "http://localhost:11434/api/generate"
_CHAT_COOLDOWN_UNTIL: Dict[str, float] = {}


def _derive_chat_endpoint_from_base_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    lower = value.rstrip("/").lower()
    if lower.endswith("/api/tags"):
        return value[: -len("/api/tags")] + "/api/chat"
    if lower.endswith("/api/chat") or lower.endswith("/api/generate") or lower.endswith("/ollama/chat"):
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return value.rstrip("/") + "/api/chat"
    return value


def _resolve_default_chat_endpoint() -> str:
    env_chat = str(os.getenv("VLM_OLLAMA_CHAT_ENDPOINT", "")).strip()
    if env_chat:
        return _derive_chat_endpoint_from_base_url(env_chat) or _DEFAULT_CHAT_ENDPOINT

    env_base = str(
        os.getenv("AGENT_OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or os.getenv("OLLAMA_HOST")
        or ""
    ).strip()
    if env_base:
        return _derive_chat_endpoint_from_base_url(env_base) or _DEFAULT_CHAT_ENDPOINT

    try:
        from modules.vlm_bridge.config_loader import load_config as load_vlm_config  # type: ignore

        cfg = load_vlm_config()
        ollama_cfg = cfg.get("ollama", {}) if isinstance(cfg, dict) else {}
        endpoint = str(ollama_cfg.get("endpoint", "")).strip()
        if endpoint:
            return _derive_chat_endpoint_from_base_url(endpoint) or _DEFAULT_CHAT_ENDPOINT
    except Exception:
        pass

    return _DEFAULT_CHAT_ENDPOINT


def _normalize_endpoint(cfg: Dict[str, Any]) -> str:
    endpoint = str((cfg or {}).get("endpoint", "")).strip()
    if not endpoint:
        return _resolve_default_chat_endpoint()

    lower = endpoint.rstrip("/").lower()
    if lower.endswith("/api/tags"):
        return endpoint[: -len("/api/tags")] + "/api/chat"
    if lower.endswith("/api/chat") or lower.endswith("/api/generate") or lower.endswith("/ollama/chat"):
        return endpoint
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint.rstrip("/") + "/api/chat"
    return endpoint


def _is_legacy_generate_endpoint(endpoint: str) -> bool:
    return endpoint.rstrip("/").endswith("/api/generate")


def _is_direct_ollama_chat_endpoint(endpoint: str) -> bool:
    return endpoint.rstrip("/").endswith("/api/chat")


def _has_real_secret(value: Any) -> bool:
    token = str(value or "").strip()
    if not token:
        return False
    lowered = token.lower()
    if lowered in {"your-google-api-key", "changeme", "replace_me", "replace-with-your-key"}:
        return False
    if "your-google-api-key" in lowered:
        return False
    return True


def _provider_hint() -> Dict[str, Any]:
    hint: Dict[str, Any] = {
        "provider": "",
        "google_key_ready": False,
    }
    try:
        from modules.ollama.config_loader import load_config as load_ollama_config  # type: ignore
    except Exception:
        return hint

    try:
        cfg = load_ollama_config(None)
    except Exception:
        return hint

    if not isinstance(cfg, dict):
        return hint

    llm_cfg = cfg.get("llm", {}) if isinstance(cfg.get("llm", {}), dict) else {}
    google_cfg = cfg.get("google_ai_studio", {}) if isinstance(cfg.get("google_ai_studio", {}), dict) else {}

    provider = str(llm_cfg.get("provider", "")).strip().lower()
    hint["provider"] = provider
    hint["google_key_ready"] = _has_real_secret(google_cfg.get("api_key"))
    return hint


def _is_in_cooldown(endpoint: str) -> bool:
    until = float(_CHAT_COOLDOWN_UNTIL.get(endpoint, 0.0))
    return until > time.time()


def _mark_cooldown(endpoint: str, seconds: float) -> None:
    _CHAT_COOLDOWN_UNTIL[endpoint] = time.time() + max(1.0, float(seconds))


def generate_text(
    prompt: str,
    ollama_cfg: Dict[str, Any],
    *,
    timeout: float = 5.0,
    response_lang: str = "tr",
) -> Optional[str]:
    if httpx is None:
        return None

    text = str(prompt or "").strip()
    if not text:
        return None

    endpoint = _normalize_endpoint(ollama_cfg)
    cooldown_s = float((ollama_cfg or {}).get("cooldown_on_failure_s", 30.0))

    hint = _provider_hint()
    provider = str(hint.get("provider", "") or "").strip().lower()

    # When Google provider is selected, direct Ollama REST endpoints are incompatible.
    # In that mode only gateway chat endpoint (/ollama/chat) should be used.
    if provider in {"google", "google_ai_studio", "gemini"}:
        if _is_direct_ollama_chat_endpoint(endpoint) or _is_legacy_generate_endpoint(endpoint):
            return None

    # Google provider selected but key is missing/placeholder: skip remote call and fall back.
    if (
        provider in {"google", "google_ai_studio", "gemini"}
        and not bool(hint.get("google_key_ready"))
        and not _is_legacy_generate_endpoint(endpoint)
    ):
        return None

    try:
        with httpx.Client(timeout=float(timeout)) as client:
            if _is_legacy_generate_endpoint(endpoint):
                model = str((ollama_cfg or {}).get("model", "llama3")).strip() or "llama3"
                resp = client.post(
                    endpoint,
                    json={"model": model, "prompt": text, "stream": False},
                )
                if resp.status_code != 200:
                    return None
                data = resp.json()
                out = str(data.get("response", "")).strip()
                return out or None

            if _is_direct_ollama_chat_endpoint(endpoint):
                model = str((ollama_cfg or {}).get("model", "gemma4:26b")).strip() or "gemma4:26b"
                num_predict = int((ollama_cfg or {}).get("num_predict", 160) or 160)
                resp = client.post(
                    endpoint,
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": text}],
                        "stream": False,
                        "options": {"temperature": 0.4, "num_predict": num_predict},
                    },
                )
                if resp.status_code != 200:
                    _mark_cooldown(endpoint, cooldown_s)
                    return None
                data = resp.json()
                msg = data.get("message", {}) if isinstance(data, dict) else {}
                out = str(msg.get("content", "") or data.get("response", "")).strip()
                _CHAT_COOLDOWN_UNTIL.pop(endpoint, None)
                return out or None

            chat_url = endpoint or _DEFAULT_CHAT_ENDPOINT
            if _is_in_cooldown(chat_url):
                return None
            # Ollama router's chat_post currently reads scalar args as query params.
            resp = client.post(
                chat_url,
                params={
                    "query": text,
                    "apply_actions": "false",
                    "response_lang": response_lang,
                },
            )
            if resp.status_code != 200:
                _mark_cooldown(chat_url, cooldown_s)
                return None
            data = resp.json()
            out = str(data.get("answer") or data.get("text") or "").strip()
            _CHAT_COOLDOWN_UNTIL.pop(chat_url, None)
            return out or None
    except Exception as exc:
        if not _is_legacy_generate_endpoint(endpoint):
            _mark_cooldown(endpoint, cooldown_s)
        logger.debug("VLM LLM request failed: %s", exc)
        return None


def default_ollama_endpoint() -> str:
    return _resolve_default_chat_endpoint()


def default_generate_endpoint() -> str:
    return _DEFAULT_GENERATE_ENDPOINT
