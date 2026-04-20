from __future__ import annotations
import os
from typing import Any, Dict
import yaml

DEFAULT_CFG = {
    "server": {"host": "0.0.0.0", "port": 8099},
    "llm": {"provider": "ollama", "single_model_mode": False},
    "ollama": {"base_url": "http://localhost:11434", "model": "gemma4:26b", "request_timeout": 60.0},
    "google_ai_studio": {
        "api_key": "",
        "model": "gemini-1.5-flash",
        "base_url": "https://generativelanguage.googleapis.com",
        "request_timeout": 60.0,
    },
    "persona": {"default": "sentry", "dir": "modules/ollama/config/personalities"},
}


def _normalize_ollama_base_url(raw: Any) -> str:
    value = str(raw or "").strip().rstrip("/")
    if not value:
        return ""
    lowered = value.lower()
    for suffix in ("/api/chat", "/api/generate", "/api/tags", "/ollama/chat"):
        if lowered.endswith(suffix):
            return value[: -len(suffix)].rstrip("/")
    return value


def _agent_cfg_candidates() -> list[str]:
    candidates: list[str] = []
    env_path = str(os.environ.get("AGENT_CFG", "")).strip()
    if env_path:
        candidates.append(env_path)

    here = os.path.dirname(__file__)
    candidates.append(os.path.normpath(os.path.join(here, "..", "..", "config", "agent.yaml")))
    candidates.append(os.path.join("config", "agent.yaml"))

    out: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        norm = os.path.normpath(path)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _load_agent_ollama_base_url() -> str:
    for path in _agent_cfg_candidates():
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception:
            continue

        if not isinstance(raw, dict):
            continue

        agent_cfg = raw.get("agent", {}) if isinstance(raw.get("agent", {}), dict) else {}
        base_url = _normalize_ollama_base_url(agent_cfg.get("ollama_base_url"))
        if base_url:
            return base_url

    return ""


def _load_vlm_primary_hint() -> Dict[str, Any]:
    path = os.environ.get("VLM_CFG", "modules/vlm_bridge/config/config.yml")
    if not path or not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except Exception:
        return {}

    if not isinstance(raw, dict):
        return {}

    llm_cfg = raw.get("llm", {}) if isinstance(raw.get("llm", {}), dict) else {}
    ollama_cfg = raw.get("ollama", {}) if isinstance(raw.get("ollama", {}), dict) else {}

    if not bool(llm_cfg.get("single_model_mode", False)):
        return {}

    model = str(llm_cfg.get("primary_model") or ollama_cfg.get("model") or "").strip()
    provider = str(llm_cfg.get("provider", "")).strip()
    return {
        "single_model_mode": True,
        "model": model,
        "provider": provider,
    }


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    path = config_path or os.environ.get("OLLAMA_CFG", "modules/ollama/config/config.yml")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    # merge shallow
    cfg = DEFAULT_CFG.copy()
    for k, v in (data or {}).items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v

    # Keep module-level config simple: centralized runtime URL can be sourced from agent.yaml.
    agent_base_url = _load_agent_ollama_base_url()
    if agent_base_url:
        cfg.setdefault("ollama", {})["base_url"] = agent_base_url

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        _load_env_file(env_path)
    except Exception:
        # Don't fail configuration load if env parsing has issues
        pass

    _apply_env_overrides(cfg)
    return cfg


def _first_env(*keys: str) -> str:
    for key in keys:
        value = os.environ.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _to_float(raw: str, fallback: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _apply_env_overrides(cfg: Dict[str, Any]) -> None:
    llm_cfg = cfg.setdefault("llm", {})
    ollama_cfg = cfg.setdefault("ollama", {})
    google_cfg = cfg.setdefault("google_ai_studio", {})

    vlm_hint = _load_vlm_primary_hint()
    if bool(vlm_hint.get("single_model_mode", False)):
        llm_cfg["single_model_mode"] = True
        hinted_provider = str(vlm_hint.get("provider", "")).strip()
        hinted_model = str(vlm_hint.get("model", "")).strip()

        if hinted_provider and not _first_env("LLM_PROVIDER", "OLLAMA_PROVIDER"):
            llm_cfg["provider"] = hinted_provider
        if hinted_model and not _first_env("OLLAMA_MODEL"):
            ollama_cfg["model"] = hinted_model

    provider = _first_env("LLM_PROVIDER", "OLLAMA_PROVIDER")
    if provider:
        llm_cfg["provider"] = provider

    base_url = _first_env("OLLAMA_BASE_URL", "OLLAMA_HOST")
    if base_url:
        ollama_cfg["base_url"] = base_url

    model = _first_env("OLLAMA_MODEL")
    if model:
        ollama_cfg["model"] = model

    request_timeout = _first_env("OLLAMA_REQUEST_TIMEOUT")
    if request_timeout:
        ollama_cfg["request_timeout"] = _to_float(request_timeout, 60.0)

    google_key = _first_env("GOOGLE_API_KEY")
    if google_key:
        google_cfg["api_key"] = google_key

    google_model = _first_env("GOOGLE_MODEL")
    if google_model:
        google_cfg["model"] = google_model


def _load_env_file(env_path: str) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ.

    Existing environment variables are not overwritten (useful for CI/local overrides).
    Lines beginning with '#' are ignored.
    """
    if not env_path or not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            # strip optional quotes
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if key:
                os.environ.setdefault(key, val)
