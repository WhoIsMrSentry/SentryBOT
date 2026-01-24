"""MARK: Google Gemini LLM — Gemini API with auto file handling"""

from pathlib import Path
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3] / "ENV" / ".env")

import os
import asyncio
from google import genai
from google.genai import types
from modules.llm._helper import build_messages, tool_loop, to_schema

# MARK: Setup
MODEL = "gemini-2.5-flash-lite-preview-06-17"
_client = None


def _check_api_key():
    """Health check for __init__.py"""
    if not os.getenv("GEMINI_API_KEY"):
        raise ImportError("GEMINI_API_KEY not set")


def _get_client():
    global _client
    if not _client:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


# MARK: Async Response
async def _response_async(
    prompt: str = "",
    instruction: str = "",
    images: list[bytes] = None,
    schema: dict = None,
    model: str = None,
    tools: list = None,
    **_,
) -> str:
    """Async Gemini response."""
    client = _get_client().aio
    model = model or MODEL
    schema = to_schema(schema)
    
    # Build parts from messages
    parts = []
    if prompt:
        parts.append(prompt)
    if images:
        for img in images:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/jpeg"))
    
    # MARK: Config
    config = types.GenerateContentConfig(
        system_instruction=instruction or None,
        response_mime_type="application/json" if schema else None,
        response_schema=schema if schema else None,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(
            disable=False, maximum_remote_calls=30
        ) if tools else None,
    )
    
    result = await client.models.generate_content(model=model, contents=parts, config=config)
    return result.text


# MARK: Sync Response (main entry)
def response(
    prompt: str = "",
    instruction: str = "",
    messages: list[dict] = None,
    images: list[bytes] = None,
    schema: dict = None,
    model: str = None,
    tools: list = None,
    max_steps: int = 10,
    history: list = None,
    **_,
):
    """Sync Gemini response. Uses asyncio.to_thread for async call."""
    schema = to_schema(schema)
    msgs = build_messages(prompt, instruction, messages, images)
    
    def chat(m, td):
        # Extract prompt and images from messages
        p = m[-1]["content"] if m else ""
        imgs = m[-1].get("images") if m else None
        sys_instr = m[0]["content"] if m and m[0].get("role") == "system" else ""
        
        text = asyncio.run(_response_async(
            prompt=p,
            instruction=sys_instr,
            images=imgs,
            schema=schema,
            model=model,
            tools=td,
        ))
        return {"message": {"content": text}}
    
    return tool_loop(chat, msgs, tools, max_steps, history=history)


# MARK: Test
if __name__ == "__main__":
    from pydantic import BaseModel
    
    class Nums(BaseModel):
        n: list[int]
    
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    
    print(f"Google Gemini | {MODEL}")
    print("\n--- Basic ---")
    print(response("Say hi briefly")["content"])
    print("\n--- Schema ---")
    print(response("Numbers 1-3", schema=Nums)["content"])
    print("\n--- Tools ---")
    print(response("What is 2+3?", tools=[add])["content"])
