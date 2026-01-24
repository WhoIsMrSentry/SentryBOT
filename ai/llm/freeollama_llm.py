"""MARK: OllamaFreeAPI LLM — free cloud Ollama (last resort)"""

from pathlib import Path
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ollamafreeapi import OllamaFreeAPI
from middleware import log
from modules.llm._helper import build_messages, tool_loop, to_schema

# MARK: Client Setup
client = OllamaFreeAPI()
models = client.list_models()
MODEL = next((m for m in ["gpt-oss:20b", "mistral-nemo:custom"] if m in models), models[0])
_use_inject = False


# MARK: Response
def response(
    prompt: str = "",
    *,
    instruction: str = "",
    messages: list[dict] = None,
    images: list[bytes] = None,
    schema: dict = None,
    model: str = None,
    tools: list = None,
    options: dict = None,
    max_steps: int = 10,
    history: list = None,
    **_,
):
    global _use_inject
    schema = to_schema(schema)
    msgs = build_messages(prompt, instruction, messages, images)

    def chat(m, td):
        return client.chat(model=model or MODEL, messages=m,
                           tools=td, format=schema, options=options or {})

    # Try native tools, auto-switch to inject on failure
    if tools and not _use_inject:
        result = tool_loop(chat, msgs, tools, max_steps, history=history)
        if "not support" not in result.get("content", "").lower():
            return result
        _use_inject = True
        log.warning("OllamaFreeAPI: native tools unsupported, switching to inject")
        msgs = build_messages(prompt, instruction, messages, images)

    return tool_loop(chat, msgs, tools, max_steps, inject=True, history=history)


# MARK: Test
if __name__ == "__main__":
    from pydantic import BaseModel
    class Nums(BaseModel):
        n: list[int]

    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    print(f"OllamaFreeAPI | {MODEL}")
    print("\n--- Basic ---")
    print(response("Say hi briefly")["content"])
    print("\n--- Schema ---")
    print(response("Numbers 1-3", schema=Nums)["content"])
    print("\n--- Tools ---")
    print(response("What is 2+3?", tools=[add])["content"])
