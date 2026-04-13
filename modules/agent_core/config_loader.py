from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict

import yaml

_MODULE_DIR = Path(__file__).parent
_DEFAULT_CFG_PATH = _MODULE_DIR / "config" / "config.yml"
_DEFAULT_DOTENV_PATHS = (
    _MODULE_DIR / ".env",
    _MODULE_DIR.parent / "ollama" / ".env",
    _MODULE_DIR.parent.parent / ".env",
)


def _deep_update(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _first_env(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _safe_float(value: str, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: str, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: str, fallback: bool) -> bool:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return fallback


def _load_vlm_primary_hint() -> Dict[str, Any]:
    path = os.environ.get("VLM_CFG", "modules/vlm_bridge/config/config.yml")
    if not path or not Path(path).exists():
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
    fallback_model = str(llm_cfg.get("clm_fallback_model", "")).strip()
    return {
        "model": model,
        "provider": provider,
        "clm_fallback_enabled": bool(llm_cfg.get("clm_fallback_enabled", True)),
        "clm_fallback_model": fallback_model,
        "fallback_on_missing_model": bool(llm_cfg.get("fallback_on_missing_model", True)),
        "fallback_on_error": bool(llm_cfg.get("fallback_on_error", True)),
    }


def load_config(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    for dotenv_path in _DEFAULT_DOTENV_PATHS:
        _load_dotenv(dotenv_path)

    cfg_path = Path(path) if path else _DEFAULT_CFG_PATH
    if not cfg_path.exists():
        cfg_path = _DEFAULT_CFG_PATH
    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    # Env overrides
    env: Dict[str, Any] = {}

    vlm_hint = _load_vlm_primary_hint()
    if vlm_hint:
        hinted_model = str(vlm_hint.get("model", "")).strip()
        hinted_provider = str(vlm_hint.get("provider", "")).strip()
        if hinted_model and not _first_env("AGENT_MODEL", "AGENT_OLLAMA_MODEL", "OLLAMA_MODEL"):
            env.setdefault("agent", {})["model"] = hinted_model
            env.setdefault("llm", {})["model"] = hinted_model
        if hinted_provider and not _first_env("LLM_PROVIDER"):
            env.setdefault("llm", {})["provider"] = hinted_provider

        env.setdefault("llm", {})["clm_fallback_enabled"] = bool(vlm_hint.get("clm_fallback_enabled", True))
        if str(vlm_hint.get("clm_fallback_model", "")).strip():
            env.setdefault("llm", {})["clm_fallback_model"] = str(vlm_hint.get("clm_fallback_model", "")).strip()
        env.setdefault("llm", {})["fallback_on_missing_model"] = bool(vlm_hint.get("fallback_on_missing_model", True))
        env.setdefault("llm", {})["fallback_on_error"] = bool(vlm_hint.get("fallback_on_error", True))

    model = _first_env("AGENT_MODEL", "AGENT_OLLAMA_MODEL", "OLLAMA_MODEL")
    if model:
        env.setdefault("agent", {})["model"] = model
        env.setdefault("llm", {})["model"] = model

    provider = _first_env("LLM_PROVIDER")
    if provider:
        env.setdefault("llm", {})["provider"] = provider

    clm_fallback_enabled = _first_env("AGENT_CLM_FALLBACK_ENABLED")
    if clm_fallback_enabled:
        env.setdefault("llm", {})["clm_fallback_enabled"] = _safe_bool(clm_fallback_enabled, True)

    clm_fallback_model = _first_env("AGENT_CLM_FALLBACK_MODEL")
    if clm_fallback_model:
        env.setdefault("llm", {})["clm_fallback_model"] = clm_fallback_model

    fallback_on_missing_model = _first_env("AGENT_FALLBACK_ON_MISSING_MODEL")
    if fallback_on_missing_model:
        env.setdefault("llm", {})["fallback_on_missing_model"] = _safe_bool(fallback_on_missing_model, True)

    fallback_on_error = _first_env("AGENT_FALLBACK_ON_ERROR")
    if fallback_on_error:
        env.setdefault("llm", {})["fallback_on_error"] = _safe_bool(fallback_on_error, True)

    cooldown = _first_env("AGENT_COOLDOWN_S")
    if cooldown:
        env.setdefault("agent", {})["cooldown_s"] = _safe_float(cooldown, 1.0)

    max_steps = _first_env("AGENT_MAX_STEPS", "AGENT_MAX_TOOL_LOOPS")
    if max_steps:
        env.setdefault("agent", {})["max_steps"] = _safe_int(max_steps, 6)

    request_timeout = _first_env("AGENT_OLLAMA_REQUEST_TIMEOUT", "OLLAMA_REQUEST_TIMEOUT")
    if request_timeout:
        env.setdefault("agent", {})["request_timeout"] = _safe_float(request_timeout, 60.0)

    explicit_provider = _first_env("LLM_PROVIDER")
    ollama_base_url = _first_env("AGENT_OLLAMA_BASE_URL", "OLLAMA_BASE_URL", "OLLAMA_HOST")
    if ollama_base_url:
        env.setdefault("agent", {})["ollama_base_url"] = ollama_base_url
        env.setdefault("llm", {})["base_url"] = ollama_base_url
        if not explicit_provider:
            env.setdefault("llm", {})["provider"] = "ollama"

    tri_layer_enabled = _first_env("AGENT_TRI_LAYER_ENABLED")
    if tri_layer_enabled:
        env.setdefault("tri_layer", {})["enabled"] = _safe_bool(tri_layer_enabled, True)

    router_max = _first_env("AGENT_ROUTER_MAX_SUBAGENTS")
    if router_max:
        env.setdefault("tri_layer", {}).setdefault("router", {})["max_subagents"] = _safe_int(router_max, 2)

    subagent_max_steps = _first_env("AGENT_SUBAGENT_MAX_STEPS")
    if subagent_max_steps:
        env.setdefault("tri_layer", {}).setdefault("subagent", {})["max_steps"] = _safe_int(subagent_max_steps, 2)

    persona_num_predict = _first_env("AGENT_PERSONA_NUM_PREDICT")
    if persona_num_predict:
        env.setdefault("tri_layer", {}).setdefault("persona", {})["num_predict"] = _safe_int(persona_num_predict, 220)

    return _deep_update(data, env)
