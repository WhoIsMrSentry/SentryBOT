"""Interactive CLI tester for Persona Models + PersonaRAG + Hybrid TR/EN Bridge.

Tests Ollama persona models (`glados:latest`, `sentry:latest`, etc.) directly with
the exact `PersonaRAG` knowledge base and TR<->EN translator used by SentryBOT V5,
without requiring robot hardware (Arduino/Camera/Piper).

Usage:
    python scripts/test_persona_chat.py --persona glados
    python scripts/test_persona_chat.py --persona glados --prompt "Cave Johnson kimdir?"
    python scripts/test_persona_chat.py --persona glados --with-tools --prompt "Sinirlen ve bana Wheatley'yi anlat"
    python scripts/test_persona_chat.py --persona glados --no-translate --prompt "Tell me about Wheatley."
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.agent_core.services.tools.tool_schemas import get_all_tool_definitions  # noqa: E402
from modules.ai_provider.services.persona_rag import PersonaManager  # noqa: E402
from modules.common.config_loader import load_agent_config  # noqa: E402
from modules.common.system_prompts import persona_prompt_with_language  # noqa: E402
from modules.common.translator import get_shared_translator  # noqa: E402


def _resolve_ollama_url(cfg: Dict[str, Any], override: str) -> str:
    if str(override or "").strip():
        return str(override).strip().rstrip("/")
    for url in (
        (cfg.get("ollama") or {}).get("base_url"),
        (cfg.get("agent") or {}).get("ollama_base_url"),
        "http://127.0.0.1:11434",
    ):
        cand = str(url or "").strip().rstrip("/")
        if not cand:
            continue
        try:
            r = requests.get(f"{cand}/api/tags", timeout=1.5)
            if r.status_code == 200:
                return cand
        except Exception:
            continue
    return "http://127.0.0.1:11434"


def _build_translator(cfg: Dict[str, Any], enabled: bool):
    if not enabled:
        return None
    tcfg = dict(cfg.get("translation") or {})
    tcfg["enabled"] = True
    return get_shared_translator(tcfg)


def _run_turn(
    *,
    user_text: str,
    persona_name: str,
    mgr: PersonaManager,
    translator: Any,
    ollama_url: str,
    history: List[Dict[str, str]],
    top_k: int,
    with_tools: bool,
) -> None:
    loaded = mgr.load_persona(persona_name)
    manifest = loaded["manifest"]
    rag = loaded["rag"]
    model = str(manifest.get("model") or f"{persona_name}:latest")

    t0 = time.monotonic()
    src_lang = translator.detect_language(user_text, default="tr") if translator else "en"
    en_query = translator.to_bridge(user_text, src_lang) if (translator and src_lang != "en") else user_text

    hits = rag.recall(en_query, limit=top_k)
    lore_ctx = rag.build_prompt_context(en_query, limit=top_k)

    print(f"\n[Model] {model} ({ollama_url})")
    if en_query != user_text:
        print(f"[TR -> EN] {en_query}")
    if hits:
        print(f"[RAG Hits ({len(hits)})]")
        for i, h in enumerate(hits, 1):
            label = f"{h.get('page') or h.get('source')} | {h.get('title') or 'intro'}"
            snippet = " ".join(str(h.get("text") or "").split())[:130]
            print(f"  {i}. score={h['score']:.3f} [{label}] -> {snippet}...")
    else:
        print("[RAG Hits] (eslesme yok)")

    lang_rule = "Reply ONLY in natural English."
    sys_txt = persona_prompt_with_language(
        loaded["prompt_text"],
        lang_rule,
        lore_context=lore_ctx,
        include_tools=with_tools,
    )
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": sys_txt},
        *history[-6:],
        {"role": "user", "content": en_query},
    ]

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 2048},
    }
    if with_tools:
        payload["tools"] = get_all_tool_definitions()

    resp = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=90.0)
    resp.raise_for_status()
    msg = resp.json().get("message", {}) or {}
    tool_calls = msg.get("tool_calls") or []
    en_reply = str(msg.get("content") or "").strip()

    steps = 0
    while tool_calls and steps < 4:
        steps += 1
        print("[Tool Calls]")
        messages.append(msg)
        for tc in tool_calls:
            fn = tc.get("function") or {}
            fn_name = str(fn.get("name") or "")
            fn_args = fn.get("arguments") or {}
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except Exception:
                    fn_args = {}
            print(f"  -> {fn_name}({json.dumps(fn_args, ensure_ascii=False)})")
            if fn_name == "search_persona_knowledge":
                q = str(fn_args.get("query") or en_query)
                lim = max(1, min(6, int(fn_args.get("limit") or top_k)))
                extra_hits = rag.recall(q, limit=lim)
                tool_out = "\n".join(f"[{h.get('page')}] {h.get('text')}" for h in extra_hits) or "No matching lore chunks."
            elif fn_name == "list_personas":
                tool_out = ", ".join(p["id"] for p in mgr.list_personas())
            else:
                tool_out = f"[Simulated OK] Executed {fn_name} with {fn_args}"
            messages.append({"role": "tool", "name": fn_name, "content": tool_out})

        if en_reply:
            break
        follow_payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": 2048},
        }
        if steps < 3:
            follow_payload["tools"] = payload.get("tools")
        resp2 = requests.post(f"{ollama_url}/api/chat", json=follow_payload, timeout=90.0)
        resp2.raise_for_status()
        msg = resp2.json().get("message", {}) or {}
        tool_calls = msg.get("tool_calls") or []
        en_reply = str(msg.get("content") or "").strip()

    dt_s = round(time.monotonic() - t0, 2)
    history.append({"role": "user", "content": en_query})
    if en_reply:
        history.append({"role": "assistant", "content": en_reply})

    print(f"\n[{persona_name.upper()} (EN, {dt_s}s)]\n{en_reply}")
    if translator and src_lang != "en" and en_reply:
        tr_reply = translator.from_bridge(en_reply, src_lang)
        print(f"\n[{persona_name.upper()} -> {src_lang.upper()}]\n{tr_reply}")
    print("-" * 72)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive Persona + RAG + Ollama tester.")
    parser.add_argument("--persona", default="glados", help="Active persona (default: glados)")
    parser.add_argument("--prompt", default="", help="Run a single prompt and exit")
    parser.add_argument("--ollama-url", default="", help="Override Ollama URL")
    parser.add_argument("--top-k", type=int, default=3, help="RAG chunks per turn (default: 3)")
    parser.add_argument("--no-translate", action="store_true", help="Disable TR<->EN bridge translator")
    parser.add_argument("--with-tools", action="store_true", help="Pass native robot tool schemas to Ollama")
    args = parser.parse_args(argv)

    cfg = load_agent_config()
    ollama_url = _resolve_ollama_url(cfg, args.ollama_url)
    mgr = PersonaManager("modules/ai_provider/config/personalities")
    translator = _build_translator(cfg, enabled=not args.no_translate)
    histories: Dict[str, List[Dict[str, str]]] = {}
    current_persona = args.persona.strip().lower()

    try:
        if args.prompt:
            _run_turn(
                user_text=args.prompt,
                persona_name=current_persona,
                mgr=mgr,
                translator=translator,
                ollama_url=ollama_url,
                history=histories.setdefault(current_persona, []),
                top_k=args.top_k,
                with_tools=bool(args.with_tools),
            )
            return 0

        print(f"Persona + RAG Test Console | active={current_persona} | ollama={ollama_url} | tools={bool(args.with_tools)}")
        print("Komutlar: /persona <ad>, /rag <sorgu>, /clear, /exit")
        while True:
            try:
                line = input(f"\n({current_persona}) > ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line in {"/exit", "/quit", "q"}:
                break
            if line.startswith("/persona "):
                target = line.split(None, 1)[1].strip()
                resolved = mgr.resolve_name(target) or target
                current_persona = resolved
                print(f"[Persona degisti -> {current_persona}]")
                continue
            if line == "/clear":
                histories[current_persona] = []
                print("[Gecmis temizlendi]")
                continue
            if line.startswith("/rag "):
                q = line.split(None, 1)[1].strip()
                rag = mgr.get_rag(current_persona)
                q_en = translator.to_bridge(q, "auto") if translator else q
                for i, h in enumerate(rag.recall(q_en, limit=args.top_k), 1):
                    print(f"  {i}. score={h['score']:.3f} [{h.get('page')} | {h.get('title')}] {h['text'][:200]}")
                continue

            _run_turn(
                user_text=line,
                persona_name=current_persona,
                mgr=mgr,
                translator=translator,
                ollama_url=ollama_url,
                history=histories.setdefault(current_persona, []),
                top_k=args.top_k,
                with_tools=bool(args.with_tools),
            )
        return 0
    finally:
        mgr.close()


if __name__ == "__main__":
    raise SystemExit(main())
