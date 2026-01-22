"""MARK: LLM — auto-selects first available provider

Provider contract (each *_llm.py must export):
  MODEL: str         — model name (multimodal)
  response(...)      — Ollama-style response function
"""
import os
from middleware import log

# MARK: Provider cascade (priority order)
FORCE = os.getenv("FORCE_MODEL", "").lower()
_CASCADE = ["ollama", "colab", "cerebras", "vivgrid", "g4f", "google", "freeollama"]

_HEALTH = {
    "ollama": lambda mod: mod.client.list(),
    "colab": lambda mod: mod.client.list(),
    "google": lambda mod: mod._check_api_key(),
}

_cache = {}


def _load(name):
    if name in _cache:
        if not _cache[name]:
            raise ImportError(f"{name} unavailable")
        return _cache[name]
    try:
        mod = __import__(f"modules.llm.{name}_llm", fromlist=["_"])
        if name in _HEALTH:
            _HEALTH[name](mod)
        if not getattr(mod, "MODEL", ""):
            raise ImportError(f"{name}: no MODEL")
        _cache[name] = mod
        log.info("LLM loaded: %s (%s)", name, mod.MODEL)
        return mod
    except Exception:
        _cache[name] = False
        raise


if FORCE:
    llm = _load(FORCE)
    _provider_name = FORCE
else:
    for _name in _CASCADE:
        try:
            llm = _load(_name)
            _provider_name = _name
            break
        except Exception:
            continue
    else:
        raise ImportError("No LLM provider available")
