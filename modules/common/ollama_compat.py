"""Compatibility helpers for invoking Ollama SDK ``Client.chat`` across versions."""
from __future__ import annotations

import inspect
import re
from typing import Any

_OPTIONAL_CHAT_KWARGS = ("think", "priority", "keep_alive")
_UNEXPECTED_KW_RE = re.compile(r"unexpected keyword argument ['\"]?([a-zA-Z0-9_]+)['\"]?")


def chat_accepts_kwarg(client: Any, name: str) -> bool:
    """Return True if ``client.chat`` explicitly accepts ``name`` or ``**kwargs``."""
    chat_fn = getattr(client, "chat", None)
    if chat_fn is None:
        return False
    try:
        sig = inspect.signature(chat_fn)
    except (TypeError, ValueError):
        if name == "priority":
            return hasattr(client, "supports_priority")
        return True
    if name in sig.parameters:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


def call_ollama_chat(
    client: Any,
    *,
    optional_kwargs: tuple[str, ...] = _OPTIONAL_CHAT_KWARGS,
    **kwargs: Any,
) -> Any:
    """Invoke ``client.chat(**kwargs)``, dropping unsupported optional kwargs cleanly."""
    call_kwargs = dict(kwargs)
    for opt in optional_kwargs:
        if opt in call_kwargs and not chat_accepts_kwarg(client, opt):
            call_kwargs.pop(opt, None)

    for _ in range(len(optional_kwargs) + 1):
        try:
            return client.chat(**call_kwargs)
        except TypeError as exc:
            msg = str(exc)
            match = _UNEXPECTED_KW_RE.search(msg)
            stripped = False
            if match:
                bad_key = match.group(1)
                if bad_key in optional_kwargs and bad_key in call_kwargs:
                    call_kwargs.pop(bad_key, None)
                    stripped = True
            if not stripped:
                for opt in optional_kwargs:
                    if opt in call_kwargs and f"'{opt}'" in msg:
                        call_kwargs.pop(opt, None)
                        stripped = True
                        break
            if not stripped:
                raise
    return client.chat(**call_kwargs)


__all__ = ["call_ollama_chat", "chat_accepts_kwarg"]
