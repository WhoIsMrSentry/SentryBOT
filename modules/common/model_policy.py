"""Local-only model policy for SentryBOT.

All LLM/VLM routing is forced to local Ollama.
"""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

LOCAL_MODEL = "qwen3.5:9b"
LOCAL_PROVIDER = "ollama"
LOCAL_OLLAMA_URL = "http://whoismrsentry.local:11434"


@dataclass
class ModelSpec:
    name: str
    provider: str
    max_tokens: int = 8192
    supports_streaming: bool = True
    supports_functions: bool = True
    supports_vision: bool = True
    context_window: int = 262144
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelProfile:
    name: str
    model: str
    provider: str
    temperature: float = 0.3
    top_p: float = 0.9
    max_tokens: int = 2048
    timeout_s: float = 60.0
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "model": self.model,
            "provider": self.provider,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "timeout_s": self.timeout_s,
            **self.extra_params,
        }


class ModelPolicy:
    def __init__(self):
        self._models: Dict[str, ModelSpec] = {}
        self._profiles: Dict[str, ModelProfile] = {}
        self._default_model: Optional[str] = LOCAL_MODEL
        self._required_model: Optional[str] = LOCAL_MODEL
        self._strict_single_model = True
        self._provider_order: List[str] = [LOCAL_PROVIDER]
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register_model(ModelSpec(name=LOCAL_MODEL, provider=LOCAL_PROVIDER))
        self.register_profile(ModelProfile(
            name="ollama_default",
            model=LOCAL_MODEL,
            provider=LOCAL_PROVIDER,
            temperature=0.3,
            top_p=0.9,
            max_tokens=2048,
        ))
        self.register_profile(ModelProfile(
            name="vision_default",
            model=LOCAL_MODEL,
            provider=LOCAL_PROVIDER,
            temperature=0.2,
            top_p=0.9,
            max_tokens=1024,
        ))
        self.register_profile(ModelProfile(
            name="remote_ollama",
            model=LOCAL_MODEL,
            provider=LOCAL_PROVIDER,
            temperature=0.3,
            top_p=0.9,
            max_tokens=2048,
        ))

    def register_model(self, model: ModelSpec) -> None:
        self._models[f"{model.provider}:{model.name}"] = model
        if self._default_model is None:
            self._default_model = model.name

    def unregister_model(self, provider: str, name: str) -> bool:
        key = f"{provider}:{name}"
        if key in self._models:
            del self._models[key]
            return True
        return False

    def get_model(self, provider: str, name: str) -> Optional[ModelSpec]:
        return self._models.get(f"{provider}:{name}")

    def list_models(self, provider: Optional[str] = None) -> List[ModelSpec]:
        models = list(self._models.values())
        if provider:
            return [m for m in models if m.provider == provider]
        return models

    def register_profile(self, profile: ModelProfile) -> None:
        self._profiles[profile.name] = profile

    def get_profile(self, name: str) -> Optional[ModelProfile]:
        return self._profiles.get(name)

    def list_profiles(self) -> List[str]:
        return list(self._profiles.keys())

    def get_active_profile(self, config: Dict[str, Any]) -> Optional[ModelProfile]:
        name = self._resolve_profile_name(config)
        return self.get_profile(name) if name else None

    def _resolve_profile_name(self, config: Dict[str, Any]) -> Optional[str]:
        for key in ("runtime_profile", "realtime_profile"):
            section = config.get(key)
            if isinstance(section, dict):
                active = str(section.get("active", "")).strip()
                if active:
                    return active
        active = config.get("active_profile")
        return str(active).strip() if active else None

    def set_required_model(self, model_name: str, provider: str = "") -> None:
        self._required_model = LOCAL_MODEL

    def set_strict_single_model(self, enabled: bool) -> None:
        self._strict_single_model = bool(enabled)

    def resolve_model(self, config: Dict[str, Any]) -> Dict[str, Any]:
        llm_cfg = config.get("llm", {}) if isinstance(config.get("llm"), dict) else {}
        return {
            "provider": LOCAL_PROVIDER,
            "model": LOCAL_MODEL,
            "temperature": llm_cfg.get("temperature", 0.3),
            "enforced": True,
        }

    def get_provider_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        resolved = self.resolve_model(config)
        provider_cfg = config.get(LOCAL_PROVIDER, {})
        merged = {**resolved, **provider_cfg} if isinstance(provider_cfg, dict) else dict(resolved)
        merged["provider"] = LOCAL_PROVIDER
        merged["model"] = LOCAL_MODEL
        merged["base_url"] = self._resolve_ollama_base_url(config)
        return merged

    def _resolve_ollama_base_url(self, config: Dict[str, Any]) -> str:
        agent_cfg = config.get("agent", {}) if isinstance(config.get("agent"), dict) else {}
        llm_cfg = config.get("llm", {}) if isinstance(config.get("llm"), dict) else {}
        ollama_cfg = config.get("ollama", {}) if isinstance(config.get("ollama"), dict) else {}

        candidates = [
            agent_cfg.get("ollama_base_url"),
            llm_cfg.get("base_url"),
            ollama_cfg.get("base_url"),
            os.getenv("SENTRYBOT_OLLAMA_BASE_URL"),
            os.getenv("SENTRYBOT_REMOTE_OLLAMA_URL"),
            os.getenv("OLLAMA_BASE_URL"),
            os.getenv("AGENT_OLLAMA_BASE_URL"),
            LOCAL_OLLAMA_URL,
        ]

        for source in candidates:
            if not source:
                continue
            url = str(source).strip().rstrip("/")
            lowered = url.lower()
            if "@gateway" in lowered or ":8080" in lowered:
                continue
            return url

        return LOCAL_OLLAMA_URL


_global_policy: Optional[ModelPolicy] = None
_sync_policy_lock = threading.Lock()
_async_policy_lock = asyncio.Lock()


def get_model_policy() -> ModelPolicy:
    global _global_policy
    if _global_policy is None:
        with _sync_policy_lock:
            if _global_policy is None:
                _global_policy = ModelPolicy()
    return _global_policy


async def get_model_policy_async() -> ModelPolicy:
    global _global_policy
    async with _async_policy_lock:
        if _global_policy is None:
            _global_policy = ModelPolicy()
    return _global_policy


def set_model_policy(policy: ModelPolicy) -> None:
    global _global_policy
    _global_policy = policy


def resolve_model_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return get_model_policy().resolve_model(config)


def get_provider_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return get_model_policy().get_provider_config(config)


def set_required_model(model_name: str, provider: str = "") -> None:
    get_model_policy().set_required_model(model_name, provider)


def set_strict_single_model(enabled: bool) -> None:
    get_model_policy().set_strict_single_model(enabled)


__all__ = [
    "ModelSpec",
    "ModelProfile",
    "ModelPolicy",
    "get_model_policy",
    "get_model_policy_async",
    "set_model_policy",
    "resolve_model_config",
    "get_provider_config",
    "set_required_model",
    "set_strict_single_model",
]
