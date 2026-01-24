"""MARK: Ollama LLM — local Ollama client"""

from pathlib import Path
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ollama import Client
from modules.llm._helper import build_messages, tool_loop, to_schema

# MARK: Client Setup
client = Client(timeout=60.0)
MODEL = "qwen3.5:4b"


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
    think=None,
    keep_alive: str = "30m",
    max_steps: int = 10,
    history: list = None,
    **_,
):
    schema = to_schema(schema)
    msgs = build_messages(prompt, instruction, messages, images)

    def chat(m, td):
        return client.chat(model=model or MODEL, messages=m, tools=td,
                           format=schema, options={"num_ctx": 8192, **(options or {})},
                           think=think, keep_alive=keep_alive)

    return tool_loop(chat, msgs, tools, max_steps, history=history)


# MARK: Test
if __name__ == "__main__":
    from pydantic import BaseModel
    class Nums(BaseModel):
        n: list[int]

    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    print(f"Ollama | {MODEL}")
    print("\n--- Basic ---")
    print(response("Say hi briefly")["content"])
    print("\n--- Schema ---")
    print(response("Numbers 1-3", schema=Nums)["content"])
    print("\n--- Tools ---")
    print(response("What is 2+3?", tools=[add])["content"])
