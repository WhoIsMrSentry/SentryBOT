"""MARK: G4F LLM — free GPT API (dynamic model fallback chain)"""

from pathlib import Path
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import g4f
from g4f.client import Client
from middleware import log
from modules.llm._helper import (get_working_models, to_schema, build_messages,
                                  tool_loop, inject_schema_hint)

# MARK: Client Setup
client = Client()
WORKING_MODELS = get_working_models()
MODEL = WORKING_MODELS[0][0] if WORKING_MODELS else ""


# MARK: Single call with fallback chain
def _call(msgs, model, tool_defs, schema, web_search):
    candidates = [(model, next((p for m, p in WORKING_MODELS if m == model), None))] if model else WORKING_MODELS
    last_err = None
    for m, prov in candidates:
        kw = {"model": m, "messages": list(msgs)}
        if schema:      kw["response_format"] = {"type": "json_object"}
        if tool_defs:   kw["tools"] = tool_defs
        if web_search:  kw["web_search"] = True
        if prov:        kw["provider"] = getattr(g4f.Provider, prov, None)
        try:
            resp = client.chat.completions.create(**kw)
            log.info("G4F: %s @ %s", getattr(resp, "model", m), getattr(resp, "provider", prov))
            return resp
        except Exception as e:
            last_err = e
            log.warning("G4F: %s @ %s — %s", m, prov, str(e)[:60])
    raise RuntimeError(f"All G4F models failed. Last: {last_err}")


# MARK: Response
def response(
    prompt: str = "",
    *,
    instruction: str = "",
    messages: list[dict] = None,
    images: list = None,
    schema: dict = None,
    model: str = "",
    tools: list = None,
    web_search: bool = False,
    max_steps: int = 10,
    history: list = None,
    **_,
):
    schema = to_schema(schema)
    msgs = build_messages(prompt, instruction, messages, images)
    inject_schema_hint(msgs, schema)

    def chat(m, td):
        return _call(m, model, td, schema, web_search)

    return tool_loop(chat, msgs, tools, max_steps, fmt="openai", history=history)


# MARK: Test
if __name__ == "__main__":
    from pydantic import BaseModel
    class Nums(BaseModel):
        nums: list[int]
        summary: str

    def add(a: int, b: int, c: int) -> int:
        """Add 3 numbers.

        Args:
            a (int): First number
            b (int): Second number
            c (int): Third number
        """
        return a + b + c

    print(f"G4F | {len(WORKING_MODELS)} models | primary: {MODEL}")
    print("\n--- Basic ---")
    print(response("Say hi briefly")["content"])
    print("\n--- Schema ---")
    print(response("Numbers 1-3", schema=Nums)["content"])
    print("\n--- Tools ---")
    print(response("What is 2+3+4 ?", tools=[add])["content"])
