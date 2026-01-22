"""MARK: LLM Helpers — converters, tool loop, model fetch."""

import json, re
from base64 import b64encode

import httpx
from pydantic_ai import Tool as PaiTool
from middleware import log

_G4F_URL = "https://raw.githubusercontent.com/maruf009sultan/g4f-working/refs/heads/main/working/working_results.txt"
_G4F_TOOL_MODELS = [("openai", "PollinationsAI")]


# MARK: ── CONVERTERS ──

def to_schema(schema):
    """Pydantic class | dict | None → dict."""
    if isinstance(schema, type) and hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()
    return schema


def fn_to_tool(fn):
    """MARK: Python function → OpenAI tool dict (via PydanticAI)."""
    td = PaiTool(fn, takes_ctx=False).tool_def
    return {"type": "function", "function": {
        "name": td.name,
        "description": (td.description or "").replace("[RELAY]", "").strip(),
        "parameters": td.parameters_json_schema}}


def data_uri(raw: bytes, ext: str = 'jpeg') -> str:
    mime = {'png': 'image/png', 'jpg': 'image/jpeg'}.get(ext, 'image/jpeg')
    return f'data:{mime};base64,{b64encode(raw).decode()}'


def sanitize(text: str) -> str:
    """Truncate base64 data URIs for logging/messages."""
    if text.startswith("data:") and ";base64," in text[:100]:
        return text[:text.index(";base64,") + 8] + f"[data:{len(text)}]"
    return text


def clean_json(text: str) -> str:
    """Strip markdown fences from JSON."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    return (m.group(1) if m else text).strip()


# MARK: ── MESSAGE BUILDERS ──

def respond(content: str, images: list[str] = None) -> dict:
    r = {"content": content}
    if images: r["images"] = images
    return r


def build_messages(prompt, instruction, messages, images):
    if messages is not None: return list(messages)
    msgs = []
    if instruction: msgs.append({"role": "system", "content": instruction})
    msg = {"role": "user", "content": prompt}
    if images: msg["images"] = images
    msgs.append(msg)
    return msgs


def inject_schema_hint(msgs, schema):
    """Append JSON-schema hint to system message."""
    if not schema: return
    hint = f"\nRespond with JSON matching: {schema}"
    if msgs and msgs[0]["role"] == "system":
        msgs[0]["content"] += hint
    else:
        msgs.insert(0, {"role": "system", "content": hint.strip()})


# MARK: ── TOOL LOOP ──

def _run_tool(fn_map, name, args, step, max_steps):
    """Execute tool, returns (result, is_relay)."""
    fn = fn_map.get(name)
    if not fn: return f"Unknown tool: {name}", False
    if isinstance(args, str): args = json.loads(args)
    log.info("[%d/%d] %s(%s)", step + 1, max_steps, name,
             json.dumps(args) if isinstance(args, dict) else args)
    try:
        return fn(**args), "[RELAY]" in (fn.__doc__ or "")
    except Exception as e:
        return f"Error: {e}", False


def _wrap_relay(result, name, args="{}"):
    """MARK: Wrap RELAY tool result — tag with tool name + args for history."""
    d = result if isinstance(result, dict) else {"content": str(result)}
    d["_tool"] = name
    d["_tool_args"] = args if isinstance(args, str) else json.dumps(args)
    return d


def tool_loop(chat_fn, msgs, tools, max_steps, fmt="ollama", *, inject=False, history=None):
    """MARK: Unified tool loop — returns {content, [images], [_tool]}.
    If history list is passed, auto-extends it with proper OpenAI tool call format.
    """
    user_msg = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
    result = _tool_loop_inner(chat_fn, msgs, tools, max_steps, fmt, inject=inject)
    # MARK: Auto-extend history by reference
    if history is not None:
        history.append({"role": "user", "content": user_msg})
        if result.get("_tool"):
            history += [{"role": "assistant", "content": "", "tool_calls": [
                {"id": "r0", "type": "function", "function": {
                    "name": result["_tool"], "arguments": result.get("_tool_args", "{}")}}]},
                {"role": "tool", "tool_call_id": "r0", "content": result["content"]}]
        else:
            history.append({"role": "assistant", "content": result["content"]})
    return result


def _tool_loop_inner(chat_fn, msgs, tools, max_steps, fmt="ollama", *, inject=False):
    """Inner tool loop — handles native + inject modes."""
    fn_map = {t.__name__: t for t in tools if callable(t)} if tools else {}
    openai = fmt == "openai"

    # MARK: No tools → simple chat
    if not fn_map:
        try:
            msg = (chat_fn(msgs, None).choices[0].message if openai
                   else chat_fn(msgs, None).message)
            return {"content": msg.content or ""}
        except Exception as e:
            return {"content": f"Error: {e}"}

    if inject:
        return _inject_loop(chat_fn, msgs, tools, fn_map, max_steps)

    # MARK: Native tool-call loop
    td = [fn_to_tool(t) for t in tools if callable(t)] if openai else tools
    for step in range(max_steps):
        try:
            resp = chat_fn(msgs, td)
        except Exception as e:
            return {"content": f"Error: {e}"}

        msg = resp.choices[0].message if openai else resp.message
        if not msg.tool_calls:
            return {"content": msg.content or ""}

        # Append assistant message
        if openai:
            msgs.append({"role": "assistant", "tool_calls": [
                {"id": getattr(tc, "id", None) or f"call_{i}", "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments if isinstance(tc.function.arguments, str)
                              else json.dumps(tc.function.arguments)}}
                for i, tc in enumerate(msg.tool_calls)]})
        else:
            msgs.append(msg)

        # Execute tools
        for i, tc in enumerate(msg.tool_calls):
            result, relay = _run_tool(fn_map, tc.function.name, tc.function.arguments, step, max_steps)
            if relay:
                return _wrap_relay(result, tc.function.name, tc.function.arguments)
            tool_msg = {"role": "tool", "content": sanitize(str(result))}
            if openai: tool_msg["tool_call_id"] = getattr(tc, "id", None) or f"call_{i}"
            else:      tool_msg["tool_name"] = tc.function.name
            msgs.append(tool_msg)

    return {"content": f"Reached max {max_steps} steps."}


# MARK: ── INJECT FALLBACK (text-based tool selection for limited models) ──

_INJECT_PROMPT = """Available tools:
{tools}

Pick the SINGLE most relevant tool. Respond ONLY with: {{"tool_call": {{"name": "...", "arguments": {{...}}}}}}
If no tool is needed, respond with: {{"done": true}}"""


def _parse_tool_call(text):
    """Parse JSON tool_call from text."""
    text = re.sub(r'```\w*\n?|```', '', text).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "tool_call" in obj: return obj["tool_call"]
    except (json.JSONDecodeError, ValueError): pass
    m = re.search(r'\{[^{}]*"tool_call"\s*:\s*\{.*\}\s*\}', text, re.DOTALL)
    if m:
        try: return json.loads(m.group()).get("tool_call")
        except (json.JSONDecodeError, ValueError): pass
    return None


def _inject_loop(chat_fn, msgs, tools, fn_map, max_steps):
    """MARK: Two-phase inject — tool selection → answer generation."""
    schemas = json.dumps([fn_to_tool(t)["function"] for t in tools if callable(t)], ensure_ascii=False)
    tool_msgs = list(msgs)
    hint = _INJECT_PROMPT.format(tools=schemas)
    if tool_msgs and tool_msgs[0]["role"] == "system":
        tool_msgs[0] = {**tool_msgs[0], "content": tool_msgs[0]["content"] + "\n\n" + hint}
    else:
        tool_msgs.insert(0, {"role": "system", "content": hint})

    # Phase 1: tool calls
    results = []
    for step in range(min(max_steps, 3)):
        try:
            content = chat_fn(tool_msgs, None).message.content or ""
        except Exception: break
        tc = _parse_tool_call(content)
        if not tc or "name" not in tc: break
        result, relay = _run_tool(fn_map, tc["name"], tc.get("arguments", {}), step, max_steps)
        if relay:
            return _wrap_relay(result, tc["name"], tc.get("arguments", {}))
        results.append((tc["name"], str(result)))
        tool_msgs.append({"role": "assistant", "content": f"[called {tc['name']}]"})
        tool_msgs.append({"role": "user", "content": f"Result: {sanitize(str(result))}\nNeed another tool? If not: {{\"done\": true}}"})

    # Phase 2: answer from tool results
    answer_msgs = list(msgs)
    if results:
        ctx = "\n".join(f"• {n}: {sanitize(r)[:500]}" for n, r in results)
        answer_msgs.append({"role": "user", "content": f"Tool results:\n{ctx}\n\nAnswer based on these."})
    try:
        return {"content": chat_fn(answer_msgs, None).message.content or ""}
    except Exception as e:
        return {"content": f"Error: {e}"}


# MARK: ── G4F MODEL FETCH ──

def get_working_models() -> list[tuple[str, str]]:
    """Fetch (model, provider) pairs — tool-capable first."""
    try:
        r = httpx.get(_G4F_URL, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.warning("G4F model fetch failed: %s", e)
        return []
    text_models = [(parts[1], parts[0]) for line in r.text.strip().splitlines()
                   if len(parts := line.strip().split("|")) == 3 and parts[2] == "text"]
    tool_set = {m for m, _ in _G4F_TOOL_MODELS}
    tool = [(m, p) for m, p in text_models if m in tool_set]
    rest = [(m, p) for m, p in text_models if m not in tool_set]
    log.info("G4F: %d tool-capable + %d others", len(tool), len(rest))
    return tool + rest
