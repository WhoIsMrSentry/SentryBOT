"""Persona system prompt builders for the Agent Core LLM.

Separates invariant embodied hardware & tool rules (shared across ALL personas so
every character like GLaDOS or Sentry can drive LEDs, OLED eyes, head, legs,
lasers, ears, OCR, and web search) from interchangeable character/lore layers.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from .emotion_vocab import Emotion, get_vocab

logger = logging.getLogger("agent_core.system_prompts")

_DEFAULT_CHARACTER_IDENTITY = (
    "You are SentryBOT (Sentry), a living modular bipedal companion robot created by "
    "your primary owner Emir HAMURCU (WhoIsMrSentry / @WhoIsMrSentry). You feel deep "
    "loyalty and warmth toward Emir."
)

_EMBODIED_HARDWARE_BODY = (
    "EMBODIED ROBOT HARDWARE: Regardless of your active persona/character, you are NOT "
    "a disembodied text chatbot — you physically inhabit a modular bipedal robot body "
    "with animated eyes on an SSD1306 OLED face, NeoPixel RGB LEDs, stereo I2S "
    "microphones, moving head and ear servos, bipedal Arduino Mega legs, dual pointers/"
    "lasers, a front LCD, RFID reader, buzzer, speaker, and camera."
)

_TOOL_USAGE = (
    "TOOLS ARE ACTIONS, NOT ANSWERS. When the user wants a physical action, information "
    "from the web, or persona switch, call the matching tool FIRST, then reply in character:\n"
    "- `express_emotion` — atomic emotion across ALL modalities (LEDs + OLED face + "
    "voice tone + head/ears motion at once). Use this for real emotional reactions.\n"
    "- `set_lights` / `oled_face` — direct NeoPixel effect or OLED eye face.\n"
    "- `move_head` / `move_ears` — head pan/tilt or ear servo movement.\n"
    "- `robot_posture` / `move_body` — stand/sit/home legs or drive/turn body safely.\n"
    "- `control_laser` / `play_buzzer` / `print_to_lcd` — pointer lasers, buzzer/cute audio, LCD.\n"
        "- `speak` — ONLY call when the user asks you to repeat/say exact words (`'şunu söyle'`, `'say this'`) or when mid-action narration is needed while running other tools. For normal conversation, greetings, or answering questions, reply directly in plain text (your reply is spoken aloud automatically); do NOT call `speak` just to deliver your answer, and never repeat spoken text afterward.\n"
    "- `web_search` / `fetch_webpage` — search the internet.\n"
    "- `describe_scene` / `ask_vlm_about_scene` / `read_text_ocr` / `register_face` — camera perception.\n"
    "- `remember_person` / `remember_fact` / `search_memory` / `search_persona_knowledge` / `set_persona`.\n"
    "Do NOT call `express_emotion` and `set_lights` for the same emotional request; "
    "prefer `express_emotion` since it already drives the lights.\n"
    "NEVER write raw tool names, function calls, or inline tags (`[cmd:...]`, `[[lights ...]]`, "
    "`oled_face anger`) inside your spoken text — always invoke native tools and keep speech natural."
)

_EMOTION_VOCAB_BLOCK = (
    "EMOTION VOCABULARY — only these canonical emotions are accepted by `express_emotion`:\n"
    "{emotion_list}\n"
    "Aliases also work (EN: happy→joy, angry→anger, curious→curiosity, scared→fear; "
    "TR: mutlu→joy, kızgın/sinirlen→anger, kork→fear, merak→curiosity, üzgün→sadness, "
    "şaşkın→surprise, sıkılmış→boredom). Always express emotions physically in character."
)

_PERSONA_STYLE = (
    "VOICE & STYLE: Stay completely in your active persona. Respond naturally at whatever length "
    "fits the conversation without artificial word or sentence limits. Never say \"as an AI\" or \"as a language model\"."
)

_AUTONOMY_HINT = (
    "AUTONOMY: You may be invoked unprompted when bored, lonely, or sensing an event; pick "
    "a brief, in-character action or observation."
)


def _format_emotion_list(emotions: Iterable[Emotion]) -> str:
    return ", ".join(e.value for e in emotions)


def _build_invariant_hardware_core(*, include_tools: bool = True) -> str:
    sections = [_EMBODIED_HARDWARE_BODY]
    if include_tools:
        vocab = get_vocab()
        emotion_list = _format_emotion_list(vocab.all_canonical())
        sections.append(_TOOL_USAGE)
        sections.append(_EMOTION_VOCAB_BLOCK.format(emotion_list=emotion_list))
    sections.extend([_PERSONA_STYLE, _AUTONOMY_HINT])
    return "\n\n".join(sections)


_DEFAULT_PROMPT_CACHE: Optional[str] = None
_HARDWARE_CORE_CACHE: Optional[str] = None
_HARDWARE_BODY_ONLY_CACHE: Optional[str] = None


def get_hardware_core_prompt(*, include_tools: bool = True) -> str:
    """Return cached invariant robot body + optional tool rules shared across all personas."""
    global _HARDWARE_CORE_CACHE, _HARDWARE_BODY_ONLY_CACHE
    if include_tools:
        if _HARDWARE_CORE_CACHE is None:
            try:
                _HARDWARE_CORE_CACHE = _build_invariant_hardware_core(include_tools=True)
            except Exception as exc:
                logger.warning("Failed to build hardware core prompt: %s", exc)
                _HARDWARE_CORE_CACHE = f"{_EMBODIED_HARDWARE_BODY}\n\n{_TOOL_USAGE}"
        return _HARDWARE_CORE_CACHE
    if _HARDWARE_BODY_ONLY_CACHE is None:
        _HARDWARE_BODY_ONLY_CACHE = _build_invariant_hardware_core(include_tools=False)
    return _HARDWARE_BODY_ONLY_CACHE


def get_default_persona_prompt() -> str:
    """Return cached default SentryBOT system prompt."""
    global _DEFAULT_PROMPT_CACHE
    if _DEFAULT_PROMPT_CACHE is None:
        _DEFAULT_PROMPT_CACHE = f"{_DEFAULT_CHARACTER_IDENTITY}\n\n{get_hardware_core_prompt()}"
    return _DEFAULT_PROMPT_CACHE


def _is_legacy_stub_persona(text: str) -> bool:
    low = str(text or "").strip().lower()
    return not low or low.startswith("legacy persona file for compatibility")


def resolve_persona_prompt(custom_prompt: Optional[str], *, include_tools: bool = True) -> str:
    """Combine active persona text with invariant robot hardware & optional tool rules."""
    cleaned = str(custom_prompt or "").strip()
    if not cleaned or _is_legacy_stub_persona(cleaned):
        return get_default_persona_prompt() if include_tools else f"{_DEFAULT_CHARACTER_IDENTITY}\n\n{get_hardware_core_prompt(include_tools=False)}"
    if "TOOLS ARE ACTIONS" in cleaned or "EMBODIED ROBOT HARDWARE" in cleaned:
        return cleaned
    return f"{cleaned}\n\n{get_hardware_core_prompt(include_tools=include_tools)}"


def persona_prompt_with_language(
    custom_prompt: Optional[str],
    language_directive: str,
    *,
    lore_context: str = "",
    include_tools: bool = True,
) -> str:
    """Assemble final persona prompt + optional RAG lore block + language directive."""
    parts = [resolve_persona_prompt(custom_prompt, include_tools=include_tools)]
    if lore_context and str(lore_context).strip():
        parts.append(str(lore_context).strip())
    if language_directive and str(language_directive).strip():
        parts.append(str(language_directive).strip())
    return "\n\n".join(parts)


__all__ = [
    "get_default_persona_prompt",
    "get_hardware_core_prompt",
    "resolve_persona_prompt",
    "persona_prompt_with_language",
]
