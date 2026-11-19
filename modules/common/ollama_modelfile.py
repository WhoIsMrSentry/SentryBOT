"""Ollama Modelfile renderer, parser, and remote model builder for SentryBOT personas.

Every persona (e.g. `sentry:latest`, `glados:latest`, custom characters) is derived
from the shared base model (`nemotron-3.5-bolt:e4b`) and pushed to the remote PC
Ollama server via `/api/create`.
"""
from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple

from modules.common.persona_scope import normalize_persona_id
from modules.common.system_prompts import get_hardware_core_prompt

logger = logging.getLogger("common.ollama_modelfile")

DEFAULT_BASE_MODEL = "nemotron-3.5-bolt:e4b"
DEFAULT_TEMPLATE = "{{ .Prompt }}"
DEFAULT_RENDERER = "gemma4-nemotron"
DEFAULT_PARSER = "gemma4"
DEFAULT_PARAMETERS: Dict[str, Any] = {
    "draft_num_predict": 7,
    "num_predict": 4096,
    "temperature": 1,
    "top_k": 64,
    "top_p": 0.95,
}


def _coerce_param_value(raw: str) -> Any:
    val = str(raw or "").strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        return val


def parse_modelfile(modelfile_text: str) -> Dict[str, Any]:
    """Parse standard Ollama Modelfile directives into structured `/api/create` fields."""
    text = str(modelfile_text or "")
    parsed: Dict[str, Any] = {
        "from": "",
        "template": "",
        "renderer": "",
        "parser": "",
        "system": "",
        "parameters": {},
    }

    sys_match = re.search(r'(?ims)^SYSTEM\s+"""(.*?)"""', text)
    if sys_match:
        parsed["system"] = sys_match.group(1).strip()
        text_wo_sys = text[: sys_match.start()] + text[sys_match.end() :]
    else:
        sys_line = re.search(r'(?im)^SYSTEM\s+"([^"]*)"', text)
        if sys_line:
            parsed["system"] = sys_line.group(1).strip()
            text_wo_sys = text[: sys_line.start()] + text[sys_line.end() :]
        else:
            text_wo_sys = text

    for raw_line in text_wo_sys.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        upper = line.upper()
        if upper.startswith("FROM "):
            parsed["from"] = line[5:].strip()
        elif upper.startswith("TEMPLATE "):
            parsed["template"] = line[9:].strip()
        elif upper.startswith("RENDERER "):
            parsed["renderer"] = line[9:].strip()
        elif upper.startswith("PARSER "):
            parsed["parser"] = line[7:].strip()
        elif upper.startswith("PARAMETER "):
            rest = line[10:].strip().split(None, 1)
            if len(rest) == 2:
                parsed["parameters"][rest[0]] = _coerce_param_value(rest[1])

    return parsed


def build_persona_system_prompt(persona_text: str, *, include_hardware_core: bool = True) -> str:
    """Combine a character's `persona.txt` instructions with embodied robot hardware & tool rules."""
    raw = str(persona_text or "").strip()
    lines = [line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    char_body = "\n".join(lines).strip() or "You are an embodied companion robot persona."
    if not include_hardware_core:
        return char_body
    if "EMBODIED ROBOT HARDWARE" in char_body or "TOOLS ARE ACTIONS" in char_body:
        return char_body
    return f"{char_body}\n\n{get_hardware_core_prompt()}"


def render_persona_modelfile(
    persona_name: str,
    persona_text: str,
    *,
    base_model: str = DEFAULT_BASE_MODEL,
    template: str = DEFAULT_TEMPLATE,
    renderer: str = DEFAULT_RENDERER,
    parser: str = DEFAULT_PARSER,
    parameters: Optional[Dict[str, Any]] = None,
    include_hardware_core: bool = True,
) -> str:
    """Render an Ollama Modelfile derived from `nemotron-3.5-bolt:e4b` matching `sentry/modelfile`."""
    base = str(base_model or DEFAULT_BASE_MODEL).strip()
    tmpl = str(template or DEFAULT_TEMPLATE).strip()
    rend = str(renderer or DEFAULT_RENDERER).strip()
    prs = str(parser or DEFAULT_PARSER).strip()
    params = dict(DEFAULT_PARAMETERS)
    if isinstance(parameters, dict):
        params.update(parameters)
    sys_prompt = build_persona_system_prompt(persona_text, include_hardware_core=include_hardware_core)
    safe_sys = sys_prompt.replace('"""', '\\"\\"\\"')

    param_lines = "\n".join(f"PARAMETER {k} {v}" for k, v in params.items())
    return (
        f"# SentryBOT V5 Persona Modelfile ({normalize_persona_id(persona_name)})\n"
        f"FROM {base}\n\n"
        f"TEMPLATE {tmpl}\n"
        f"RENDERER {rend}\n"
        f"PARSER {prs}\n\n"
        f"{param_lines}\n\n"
        f'SYSTEM """\n{safe_sys}\n"""\n'
    )


def load_or_build_persona_modelfile(
    persona_dir: Path,
    *,
    base_model: str = DEFAULT_BASE_MODEL,
) -> str:
    """Return existing `modelfile` or build one from `persona.txt` + `persona.yml`."""
    mf_path = Path(persona_dir) / "modelfile"
    if mf_path.is_file():
        return mf_path.read_text(encoding="utf-8", errors="replace")
    txt_path = Path(persona_dir) / "persona.txt"
    persona_txt = txt_path.read_text(encoding="utf-8", errors="replace") if txt_path.is_file() else ""
    return render_persona_modelfile(
        Path(persona_dir).name,
        persona_txt,
        base_model=base_model,
    )


def build_ollama_create_payload(model_name: str, modelfile_text: str) -> Dict[str, Any]:
    """Build a modern Ollama `/api/create` JSON payload from a Modelfile string."""
    parsed = parse_modelfile(modelfile_text)
    payload: Dict[str, Any] = {
        "model": str(model_name or "").strip(),
        "from": parsed["from"] or DEFAULT_BASE_MODEL,
        "stream": False,
    }
    if parsed["system"]:
        payload["system"] = parsed["system"]
    if parsed["template"]:
        payload["template"] = parsed["template"]
    if parsed["renderer"]:
        payload["renderer"] = parsed["renderer"]
    if parsed["parser"]:
        payload["parser"] = parsed["parser"]
    if parsed["parameters"]:
        payload["parameters"] = parsed["parameters"]
    return payload


def create_remote_ollama_model(
    model_name: str,
    modelfile_text: str,
    *,
    base_url: str,
    timeout_s: float = 90.0,
) -> Tuple[bool, str]:
    """Push a derived persona model to the remote Ollama PC via `/api/create`."""
    import requests

    target_name = str(model_name or "").strip()
    host = str(base_url or "").strip().rstrip("/")
    if not target_name or not host:
        return False, "missing model name or ollama base_url"

    url = f"{host}/api/create"
    modern_payload = build_ollama_create_payload(target_name, modelfile_text)
    try:
        resp = requests.post(url, json=modern_payload, timeout=float(timeout_s))
        if resp.status_code == 200:
            return True, f"created {target_name} from {modern_payload['from']}"
        # Older Ollama servers used {"name": ..., "modelfile": ...}
        if resp.status_code in {400, 404, 422}:
            legacy_payload = {"name": target_name, "modelfile": modelfile_text, "stream": False}
            resp2 = requests.post(url, json=legacy_payload, timeout=float(timeout_s))
            if resp2.status_code == 200:
                return True, f"created {target_name} (legacy api)"
            return False, f"HTTP {resp2.status_code}: {resp2.text[:240]}"
        return False, f"HTTP {resp.status_code}: {resp.text[:240]}"
    except Exception as exc:
        return False, str(exc)


__all__ = [
    "DEFAULT_BASE_MODEL",
    "DEFAULT_PARAMETERS",
    "DEFAULT_PARSER",
    "DEFAULT_RENDERER",
    "DEFAULT_TEMPLATE",
    "build_ollama_create_payload",
    "build_persona_system_prompt",
    "create_remote_ollama_model",
    "load_or_build_persona_modelfile",
    "parse_modelfile",
    "render_persona_modelfile",
]
