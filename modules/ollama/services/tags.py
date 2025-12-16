"""Utilities for extracting structured robot actions from LLM text output."""
from __future__ import annotations

import re
import shlex
from typing import Any, Dict, List, Tuple

_CMD_PATTERN = re.compile(r"\[cmd:(.*?)\]", re.IGNORECASE | re.DOTALL)
_BLOCK_PATTERN = re.compile(r"\[\[(.*?)\]\]", re.DOTALL)


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

    without_cmds = _CMD_PATTERN.sub(_cmd_repl, text)
    cleaned = _BLOCK_PATTERN.sub(_block_repl, without_cmds)

    actions: Dict[str, List[Any]] = {}
    if commands:
        actions["commands"] = commands
    if blocks:
        actions["blocks"] = blocks
    return cleaned.strip(), actions

__all__ = ["extract_llm_tags"]
