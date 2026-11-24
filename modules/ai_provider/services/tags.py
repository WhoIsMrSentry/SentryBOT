"""Utilities for extracting structured robot actions from LLM text output."""
from __future__ import annotations

import re
import shlex
from typing import Any, Dict, List, Tuple

_CMD_PATTERN = re.compile(r"\[cmd:(.*?)\]", re.IGNORECASE | re.DOTALL)
_BLOCK_PATTERN = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)
_THINK_BLOCK_PATTERN = re.compile(r"<think\b[^>]*>.*?(?:</think>|$)", re.IGNORECASE | re.DOTALL)
_INLINE_OLED_PATTERN = re.compile(
    r"(?:\[\s*)?\b(?:oled_face|oled)\s*(?:[:=]|\(\s*(?:expression\s*=\s*|face\s*=\s*|anim\s*=\s*)?|\s+)\s*[\"']?([a-zA-Z_]+)[\"']?\s*\)?(?:\s*\])?",
    re.IGNORECASE,
)
_INLINE_LIGHTS_PATTERN = re.compile(
    r"(?:\[\s*)?\b(?:neopixel|set_lights)\s*(?:[:=]|\(\s*(?:color\s*=\s*|palette\s*=\s*)?|\s+)\s*[\"']?(red|green|blue|yellow|purple|violet|orange|cyan|teal|white|pink|gold|off|calm_violet|sunset_gold|alert_red|ocean_teal|arctic_white|forest_green|ember_orange|polar_blue)[\"']?(?:\s+(?:mode\s*=\s*)?(breathe|pulse|solid|twinkle|blink|off))?\s*\)?(?:\s*\])?",
    re.IGNORECASE,
)
_INLINE_EMOTION_TOOL_PATTERN = re.compile(
    r"(?:\[\s*)?\b(?:express_emotion|set_emotion)\s*(?:[:=]|\(\s*(?:emotion\s*=\s*)?|\s+)\s*[\"']?(anger|angry|furious|joy|happy|sadness|sad|fear|scared|curiosity|curious|surprise|neutral|calm|excited|excitement|love|boredom|bored)[\"']?\s*\)?(?:\s*\])?",
    re.IGNORECASE,
)


def _coerce_value(value: str) -> Any:
    raw = value.strip().strip('"')
    low = raw.lower()
    if low in {"true", "false"}:
        return low == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _parse_block(body: str) -> Dict[str, Any] | None:
    try:
        tokens = shlex.split(body, posix=True)
    except ValueError:
        return None
    if not tokens:
        return None
    kind = tokens[0].strip().lower()
    attrs: Dict[str, Any] = {}
    for token in tokens[1:]:
        if "=" not in token:
            continue
        key, raw = token.split("=", 1)
        attrs[key.strip()] = _coerce_value(raw)
    return {"type": kind, "attrs": attrs}


def extract_llm_tags(text: str) -> Tuple[str, Dict[str, List[Any]]]:
    """Remove action tags from text and return cleaned text + actions."""
    commands: List[str] = []
    blocks: List[Dict[str, Any]] = []

    def _cmd_repl(match: re.Match[str]) -> str:
        cmd = match.group(1).strip().lower()
        if cmd:
            commands.append(cmd)
        return ""

    def _block_repl(match: re.Match[str]) -> str:
        parsed = _parse_block(match.group(1))
        if parsed:
            blocks.append(parsed)
        return ""

    def _inline_oled_repl(match: re.Match[str]) -> str:
        face = match.group(1).strip().lower()
        if face and face not in {"on", "off", "in", "to", "is", "ve", "ile"}:
            blocks.append({"type": "oled", "attrs": {"name": face}})
            return " "
        return match.group(0)

    def _inline_lights_repl(match: re.Match[str]) -> str:
        color = match.group(1).strip().lower()
        mode = (match.group(2) or "").strip().lower()
        attrs: Dict[str, Any] = {"palette": color}
        if mode:
            attrs["mode"] = mode
        blocks.append({"type": "lights", "attrs": attrs})
        return " "

    def _inline_emotion_repl(match: re.Match[str]) -> str:
        emo = match.group(1).strip().lower()
        blocks.append({"type": "oled", "attrs": {"name": emo}})
        blocks.append({"type": "lights", "attrs": {"emotions": [emo]}})
        return " "

    without_think = _THINK_BLOCK_PATTERN.sub(" ", text or "")
    without_cmds = _CMD_PATTERN.sub(_cmd_repl, without_think)
    cleaned = _BLOCK_PATTERN.sub(_block_repl, without_cmds)
    cleaned = _INLINE_OLED_PATTERN.sub(_inline_oled_repl, cleaned)
    cleaned = _INLINE_LIGHTS_PATTERN.sub(_inline_lights_repl, cleaned)
    cleaned = _INLINE_EMOTION_TOOL_PATTERN.sub(_inline_emotion_repl, cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

    actions: Dict[str, List[Any]] = {}
    if commands:
        actions["commands"] = commands
    if blocks:
        actions["blocks"] = blocks
    return cleaned.strip(), actions


_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+")
_STAGE_DIRECTION_CUES_RE = re.compile(
    r"\b(?:"
    r"ton\w*|tone|voice|ses\w*|başım\w*|basim\w*|başı\w*|tilts?|head|look\w*|stare\w*|glare\w*|"
    r"ifade\w*|bakış\w*|bakis\w*|jest\w*|gesture\w*|sigh\w*|gasp\w*|chuckle\w*|pause\w*|duraksama\w*|"
    r"sentez\w*|synthesiz\w*|klinik|clinical|sarcastic\w*|alayc\w*|küçümse\w*|kucumse\w*|"
    r"donuk|monoton\w*|oynat\w*|eğil\w*|egil\w*|çevir\w*|cevir\w*|expression\w*|smirk\w*|dry|kuru|"
    r"şaşkınlık|saskinlik|tiksinti|rahatsızlık"
    r")\b",
    re.IGNORECASE,
)
_PAREN_SEGMENT_RE = re.compile(r"[*_`]*\(([^()]{3,280})\)[*_`]*")


def _strip_stage_directions_and_formatting(text: str) -> str:
    """Remove emojis, roleplay/stage parentheticals, and markdown wrappers for spoken TTS."""
    out = _EMOJI_RE.sub(" ", str(text or ""))

    def _paren_repl(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if _STAGE_DIRECTION_CUES_RE.search(inner):
            return " "
        return match.group(0)

    out = _PAREN_SEGMENT_RE.sub(_paren_repl, out)
    out = out.strip()
    if re.fullmatch(r"\([^()]{3,}\)", out):
        return ""
    out = re.sub(r"`([^`]*)`", r"\1", out)
    out = re.sub(r"\*{1,3}([^*\n]+?)\*{1,3}", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    if not any(ch.isalnum() for ch in out):
        return ""
    return out


def strip_speech_control_artifacts(text: str) -> str:
    """Strip inline hardware tags, <think> blocks, emojis, stage directions, and tool directives before TTS."""
    raw = str(text or "")
    if not raw.strip():
        return ""
    cleaned, _ = extract_llm_tags(raw)
    cleaned = re.sub(r"</?think\b[^>]*>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:oled_face|set_lights|express_emotion|set_emotion|move_head|play_sound)\s*\([^)]*\)",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return _strip_stage_directions_and_formatting(cleaned)


__all__ = ["extract_llm_tags", "strip_speech_control_artifacts"]
