"""Centralized role-based Ollama model routing policy for SentryBOT.

Assigns each locally installed model to its functional responsibility:
- ``sentry:latest``: main companion / self-introduction / capabilities / persona chat
- ``qwen3.5:9b``: visual description & VLM perception ONLY
- ``qwen2.5-coder:7b``: coding, scripting, debugging, and technical code generation
- ``nemotron-3.5-bolt:e4b``: non-persona structured utility, planning, memory, translation, and worker subagents
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_CHAT_MODEL = "sentry:latest"
DEFAULT_VISION_MODEL = "nemotron-3.5-bolt:e4b"
DEFAULT_CODER_MODEL = "nemotron-3.5-bolt:e4b"
DEFAULT_UTILITY_MODEL = "nemotron-3.5-bolt:e4b"

DEFAULT_ALLOWED_MODELS: Tuple[str, ...] = (
    DEFAULT_CHAT_MODEL,
    DEFAULT_UTILITY_MODEL,
)

ROLE_CHAT = "chat"
ROLE_VISION = "vision"
ROLE_CODER = "coder"
ROLE_UTILITY = "utility"

_ROLE_FAMILY: Dict[str, str] = {
    "chat": ROLE_CHAT,
    "default": ROLE_CHAT,
    "companion": ROLE_CHAT,
    "persona": ROLE_CHAT,
    "followup": ROLE_CHAT,
    "conversation": ROLE_CHAT,
    "agent": ROLE_CHAT,
    "vision": ROLE_VISION,
    "vlm": ROLE_VISION,
    "scene_description": ROLE_VISION,
    "visual_description": ROLE_VISION,
    "coder": ROLE_CODER,
    "code": ROLE_CODER,
    "developer": ROLE_CODER,
    "technical": ROLE_CODER,
    "programming": ROLE_CODER,
    "utility": ROLE_UTILITY,
    "planner": ROLE_UTILITY,
    "reflection": ROLE_UTILITY,
    "dream_reflection": ROLE_UTILITY,
    "memory": ROLE_UTILITY,
    "consolidator": ROLE_UTILITY,
    "translator": ROLE_UTILITY,
    "translation": ROLE_UTILITY,
    "subagent": ROLE_UTILITY,
    "structured": ROLE_UTILITY,
    "fallback": ROLE_UTILITY,
}

DEFAULT_MODEL_ROLES: Dict[str, str] = {
    key: (
        DEFAULT_CHAT_MODEL
        if family == ROLE_CHAT
        else DEFAULT_VISION_MODEL
        if family == ROLE_VISION
        else DEFAULT_CODER_MODEL
        if family == ROLE_CODER
        else DEFAULT_UTILITY_MODEL
    )
    for key, family in _ROLE_FAMILY.items()
}

_IDENTITY_OR_CAPABILITY_RE = re.compile(
    r"\b("
    r"kendini\s+tan[ıi]t|kendinden\s+bahset|sen\s+kimsin|ad[ıi]n\s+ne|ismin\s+ne|"
    r"yeteneklerin(?:\s+neler)?|neler\s+yapabilirsin|ne\s+yapabilirsin|kim\s+yapt[ıi]|"
    r"sahibin\s+kim|introduce\s+yourself|who\s+are\s+you|what\s+can\s+you\s+do|"
    r"your\s+capabilities|tell\s+me\s+about\s+yourself"
    r")\b",
    re.IGNORECASE,
)

_CODER_RE = re.compile(
    r"(```|"
    r"Traceback\s+\(most\s+recent\s+call\s+last\)|"
    r"\b(?:SyntaxError|TypeError|ValueError|KeyError|AttributeError|IndentationError|ImportError)\b|"
    r"\b(?:python|javascript|typescript|c\+\+|cpp|rust|golang|bash|powershell|sql|"
    r"regex|regular\s+expression|dockerfile|pytest|unit\s+test|git\s+diff|"
    r"refactor|stack\s*trace|traceback|debug(?:ging)?|hata\s+ay[ıi]kla|"
    r"kod\s+yaz|kodu\s+yaz|kodla|script\s+yaz|betik\s+yaz|fonksiyon\s+yaz|"
    r"algoritma\s+yaz|class\s+yaz)\b|"
    r"\b(?:kodu|kodunu|program[ıi])\s+(?:d[üu]zelt|incele|a[çc][ıi]kla|optimize\s+et|[çc]evir|yaz)\b|"
    r"\b(?:write|fix|debug|explain|optimize|refactor)\s+(?:a\s+|the\s+|this\s+)?(?:code|function|class|script|query|regex|snippet|bug)\b)",
    re.IGNORECASE,
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def explicit_single_model_mode(config: Optional[Dict[str, Any]]) -> Optional[bool]:
    """Return explicit ``llm.single_model_mode`` bool if set in config, else None."""
    cfg = _as_dict(config)
    llm_cfg = _as_dict(cfg.get("llm"))
    if "single_model_mode" in llm_cfg and llm_cfg.get("single_model_mode") is not None:
        return bool(llm_cfg.get("single_model_mode"))
    if "single_model_mode" in cfg and cfg.get("single_model_mode") is not None:
        return bool(cfg.get("single_model_mode"))
    return None


def allowed_models_from_config(config: Optional[Dict[str, Any]]) -> List[str]:
    """Collect deduplicated allowed model names configured under ``llm.allowed_models``."""
    cfg = _as_dict(config)
    seen: List[str] = []

    def _extend(items: Any) -> None:
        if not isinstance(items, (list, tuple, set)):
            return
        for item in items:
            s = _clean_str(item)
            if s and s not in seen:
                seen.append(s)

    _extend(_as_dict(cfg.get("llm")).get("allowed_models"))
    _extend(_as_dict(_as_dict(cfg.get("ollama_service")).get("llm")).get("allowed_models"))
    _extend(_as_dict(_as_dict(cfg.get("vlm_bridge")).get("llm")).get("allowed_models"))
    return seen


def normalize_role_name(role: str) -> str:
    raw = _clean_str(role).lower()
    return raw if raw in _ROLE_FAMILY else ROLE_CHAT


def role_family(role: str) -> str:
    return _ROLE_FAMILY.get(_clean_str(role).lower(), ROLE_CHAT)


def infer_prompt_role(prompt: str) -> str:
    """Classify a user prompt into a model routing role without hijacking persona/identity queries."""
    text = _clean_str(prompt)
    if not text:
        return ROLE_CHAT
    if _IDENTITY_OR_CAPABILITY_RE.search(text):
        return ROLE_CHAT
    if _CODER_RE.search(text):
        return ROLE_CODER
    return ROLE_CHAT


def _pick_first(*values: Any) -> str:
    for v in values:
        s = _clean_str(v)
        if s:
            return s
    return ""


def _configured_roles_map(cfg: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for source in (
        _as_dict(_as_dict(cfg.get("models")).get("roles")),
        _as_dict(_as_dict(cfg.get("llm")).get("roles")),
    ):
        for k, v in source.items():
            key = _clean_str(k).lower()
            val = _clean_str(v)
            if key and val:
                out[key] = val
    return out


def _single_mode_model(cfg: Dict[str, Any], family: str, fallback: Optional[str]) -> str:
    llm_cfg = _as_dict(cfg.get("llm"))
    ollama_cfg = _as_dict(cfg.get("ollama"))
    agent_cfg = _as_dict(cfg.get("agent"))
    vlm_cfg = _as_dict(_as_dict(cfg.get("vlm_bridge")).get("vision_llm")) or _as_dict(cfg.get("vision_llm"))
    if family == ROLE_VISION:
        return _pick_first(
            vlm_cfg.get("model"),
            llm_cfg.get("model"),
            llm_cfg.get("primary_model"),
            ollama_cfg.get("model"),
            fallback,
            DEFAULT_VISION_MODEL,
        )
    return _pick_first(
        llm_cfg.get("model"),
        llm_cfg.get("primary_model"),
        agent_cfg.get("model"),
        ollama_cfg.get("model"),
        fallback,
        DEFAULT_CHAT_MODEL,
    )


def resolve_role_model(
    config: Optional[Dict[str, Any]],
    role: str = ROLE_CHAT,
    *,
    prompt: str = "",
    fallback: Optional[str] = None,
) -> str:
    """Resolve the model name for ``role`` (optionally inferred from ``prompt``)."""
    cfg = _as_dict(config)
    requested_role = _clean_str(role).lower()
    if not requested_role or requested_role in {"auto", "prompt"}:
        requested_role = infer_prompt_role(prompt)
    family = role_family(requested_role)

    explicit_single = explicit_single_model_mode(cfg)
    if explicit_single is True:
        return _single_mode_model(cfg, family, fallback)

    roles_map = _configured_roles_map(cfg)
    configured = _pick_first(roles_map.get(requested_role), roles_map.get(family))
    if configured:
        return configured

    llm_cfg = _as_dict(cfg.get("llm"))
    ollama_cfg = _as_dict(cfg.get("ollama"))
    agent_cfg = _as_dict(cfg.get("agent"))

    if family == ROLE_VISION:
        vlm_root = _as_dict(cfg.get("vlm_bridge"))
        vlm_vis = _as_dict(vlm_root.get("vision_llm")) or _as_dict(cfg.get("vision_llm"))
        vlm_llm = _as_dict(vlm_root.get("llm"))
        vlm_ollama = _as_dict(vlm_root.get("ollama"))
        return _pick_first(
            vlm_vis.get("model"),
            vlm_llm.get("primary_model"),
            vlm_llm.get("model"),
            vlm_ollama.get("model"),
            DEFAULT_VISION_MODEL,
            fallback,
        )

    if requested_role in {"translator", "translation"}:
        tr_cfg = _as_dict(cfg.get("translation")) or _as_dict(_as_dict(cfg.get("ollama_service")).get("translation"))
        explicit_tr = _clean_str(tr_cfg.get("model"))
        if explicit_tr:
            return explicit_tr
    elif requested_role in {"planner", "reflection", "dream_reflection"}:
        explicit_pl = _pick_first(llm_cfg.get("planner_model"), cfg.get("planner_model"))
        if explicit_pl:
            return explicit_pl
    elif requested_role in {"fallback"}:
        explicit_fb = _pick_first(llm_cfg.get("clm_fallback_model"), agent_cfg.get("clm_fallback_model"))
        if explicit_fb:
            return explicit_fb

    if explicit_single is False:
        if family == ROLE_CHAT:
            return _pick_first(
                agent_cfg.get("model"),
                llm_cfg.get("model"),
                llm_cfg.get("primary_model"),
                ollama_cfg.get("model"),
                fallback,
                DEFAULT_CHAT_MODEL,
            )
        return _pick_first(DEFAULT_MODEL_ROLES.get(requested_role), fallback, DEFAULT_MODEL_ROLES.get(family), DEFAULT_CHAT_MODEL)

    # Synthetic / minimal configs without explicit single_model_mode or models.roles preserve caller model first.
    return _pick_first(
        fallback,
        agent_cfg.get("model"),
        llm_cfg.get("model"),
        ollama_cfg.get("model"),
        DEFAULT_MODEL_ROLES.get(requested_role),
        DEFAULT_CHAT_MODEL,
    )


__all__ = [
    "DEFAULT_ALLOWED_MODELS",
    "DEFAULT_CHAT_MODEL",
    "DEFAULT_CODER_MODEL",
    "DEFAULT_MODEL_ROLES",
    "DEFAULT_UTILITY_MODEL",
    "DEFAULT_VISION_MODEL",
    "ROLE_CHAT",
    "ROLE_CODER",
    "ROLE_UTILITY",
    "ROLE_VISION",
    "allowed_models_from_config",
    "explicit_single_model_mode",
    "infer_prompt_role",
    "normalize_role_name",
    "resolve_role_model",
    "role_family",
]
