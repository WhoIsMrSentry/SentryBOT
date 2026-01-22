"""MARK: Cerebras LLM — fast inference (OpenAI-compatible)
Context:65k | 30 RPM | 900 RPH | 14k TPM
"""

from pathlib import Path
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3] / "ENV" / ".env")

import os
import openai
from modules.llm._helper import build_messages, tool_loop, to_schema

# MARK: Client Setup
_key = os.environ.get("CEREBRAS_API_KEY", "")
if not _key:
    raise ImportError("CEREBRAS_API_KEY not set")

client = openai.OpenAI(api_key=_key, base_url="https://api.cerebras.ai/v1")
MODEL = "qwen-3-235b-a22b-instruct-2507"


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
    max_steps: int = 10,
    history: list = None,
    **_,
):
    schema = to_schema(schema)
    msgs = build_messages(prompt, instruction, messages, images)

    def chat(m, td):
        kw = {"model": model or MODEL, "messages": m}
        if schema:
            kw["response_format"] = {"type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": schema}}
        if td:
            kw["tools"] = td
        return client.chat.completions.create(**kw)

    return tool_loop(chat, msgs, tools, max_steps, fmt="openai", history=history)


# MARK: Test
if __name__ == "__main__":
    from pydantic import BaseModel
    class Nums(BaseModel):
        nums: list[int]
        summary: str

    def add(a: int, b: int) -> int:
        """Add two numbers.

        Args:
            a (int): First number
            b (int): Second number
        """
        return a + b

    print(f"Cerebras | {MODEL}")
    print("\n--- Basic ---")
    print(response("Say hi briefly")["content"])
    print("\n--- Schema ---")
    print(response("Numbers 1-3", schema=Nums)["content"])
    print("\n--- Tools ---")
    print(response("What is 2+3?", tools=[add])["content"])