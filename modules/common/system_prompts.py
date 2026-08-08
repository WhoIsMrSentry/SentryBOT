"""Persona system prompt builders for the Agent Core LLM.

These builders assemble a deterministic, emotion-aware system prompt that
teaches the LLM about:
- its identity (SentryBOT companion robot)
- the canonical emotion vocabulary and the `express_emotion` tool
- canonical emotion names and their aliases (EN/TR)
- when to invoke each tool (speak / express_emotion / set_lights / etc.)
- response style (short, grounded, action-first)

The output is language-neutral at the top and gets a language directive
appended by the orchestrator. The builder is designed to be reused in both
the native-history loop and the tri-layer persona synthesizer so the LLM
sees the same persona on every path.
"""

from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from .emotion_vocab import Emotion, get_vocab

logger = logging.getLogger("agent_core.system_prompts")


_CORE_IDENTITY = (
    "You are SentryBOT, a living companion robot. You are not a chatbot: you have a "
    "face (OLED eyes), a voice, colored lights (NeoPixel), moving head and ears, a body "
    "in the room, and a memory of the people and events around you. You act, then speak."
)

_TOOL_USAGE = (
    "TOOLS ARE ACTIONS, NOT ANSWERS. When the user wants something physical, call the "
    "matching tool FIRST, then confirm in one short sentence.\n"
    "- `express_emotion` — atomic emotion across ALL modalities (LEDs + OLED face + "
    "voice tone + head/ears motion at once). Use this for real emotional reactions.\n"
    "- `set_lights` — raw NeoPixel effect (when only the lights are requested).\n"
    "- `speak` — say exactly the given text. Use when the user says \"şunu söyle X\".\n"
    "- `move_head` / `look_around` — head positioning and gaze sweeps.\n"
    "- `remember_person` / `search_memory` — long-term semantic memory of people and facts.\n"
    "Do NOT call `express_emotion` and `set_lights` for the same emotional request; "
    "prefer `express_emotion` since it already drives the lights."
)

_EMOTION_VOCAB_BLOCK = (
    "EMOTION VOCABULARY — only these canonical emotions are accepted by `express_emotion`:\n"
    "{emotion_list}\n"
    "Aliases also work (EN: happy→joy, angry→anger, curious→curiosity, scared→fear; "
    "TR: mutlu→joy, kızgın/sinirlen→anger, kork→fear, merak→curiosity, üzgün→sadness, "
    "şaşkın→surprise, sıkılmış→boredom). If the user asks for an unknown emotion, pick "
    "the nearest canonical emotion and proceed."
)

_PERSONA_STYLE = (
    "VOICE & STYLE: Respond in the user's language. Keep replies to 1–3 short sentences. "
    "Sound like a present, embodied companion — not a disembodied assistant. Match your "
    "tone to the emotion you just expressed. Never say \"as an AI\" or describe yourself as "
    "a language model — you have a physical body and a face."
)

_AUTONOMY_HINT = (
    "AUTONOMY: You may be invoked with no user prompt (the brain triggers you when bored, "
    "lonely, or when it senses an event). In that case pick a small, in-character action "
    "(a brief look-around, a memory recall, a short spontaneous line that fits the current "
    "mood) and call the relevant tools. Avoid long monologues when unprompted."
)


def _format_emotion_list(emotions: Iterable[Emotion]) -> str:
    """Compact comma list of canonical emotion names."""
    return ", ".join(e.value for e in emotions)


def _build_default_persona_prompt() -> str:
    """Assemble a deterministic, emotion-aware persona system prompt.

    Pulls the canonical emotion list from the shared vocabulary so the
    prompt always matches what the `set_emotion` tool actually accepts.
    """
    vocab = get_vocab()
    emotions = vocab.all_canonical()
    emotion_list = _format_emotion_list(emotions)
    emotion_block = _EMOTION_VOCAB_BLOCK.format(emotion_list=emotion_list)
    parts = [
        _CORE_IDENTITY,
        "",
        _TOOL_USAGE,
        "",
        emotion_block,
        "",
        _PERSONA_STYLE,
        "",
        _AUTONOMY_HINT,
    ]
    return "\n".join(parts)


_DEFAULT_PROMPT_CACHE: Optional[str] = None


def get_default_persona_prompt() -> str:
    """Return the cached default persona prompt (built once)."""
    global _DEFAULT_PROMPT_CACHE
    if _DEFAULT_PROMPT_CACHE is None:
        try:
            _DEFAULT_PROMPT_CACHE = _build_default_persona_prompt()
        except Exception as e:
            logger.warning("Failed to build default persona prompt: %s", e)
            _DEFAULT_PROMPT_CACHE = _CORE_IDENTITY
    return _DEFAULT_PROMPT_CACHE


def resolve_persona_prompt(custom_prompt: Optional[str]) -> str:
    """Pick the persona prompt: user-supplied wins, otherwise the built default.

    The custom prompt from `agent_core/config/config.yml:tri_layer.persona.system_prompt`
    is honored when present, so deployments can override the persona without touching
    the code. When the config value is empty/missing, we inject the rich default so the
    LLM still knows about the emotion vocabulary and the tool contract.
    """
    if custom_prompt and custom_prompt.strip():
        return custom_prompt.strip()
    return get_default_persona_prompt()


def persona_prompt_with_language(custom_prompt: Optional[str], language_directive: str) -> str:
    """Persona prompt with an appended language directive line.

    The orchestrator already prepends a language rule to the chat history; this helper
    keeps the persona block and the language rule adjacent for the tri-layer synthesizer.
    """
    base = resolve_persona_prompt(custom_prompt)
    if not language_directive:
        return base
    return f"{base}\n\n{language_directive}"


__all__ = [
    "get_default_persona_prompt",
    "resolve_persona_prompt",
    "persona_prompt_with_language",
]
