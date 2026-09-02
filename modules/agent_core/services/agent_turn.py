from __future__ import annotations

import os as _sentrybot_agent_turn_os

def _sentrybot_agent_turn_target_model() -> str:
    return (
        _sentrybot_agent_turn_os.environ.get("SENTRYBOT_OLLAMA_MODEL")
        or _sentrybot_agent_turn_os.environ.get("SENTRYBOT_MODEL")
        or _sentrybot_agent_turn_os.environ.get("SENTRYBOT_LLM_MODEL")
        or "qwen3.5:9b"
    ).strip()

def _sentrybot_normalize_agent_turn_model(model) -> str:
    target = _sentrybot_agent_turn_target_model()
    value = str(model or "").strip()

    if (
        not value
        or value == "qwen2.5:3b"
        or value == "qwen2.5"
        or value == "qwen2.5:latest"
        or value.startswith("qwen2.5:")
        or value.startswith("qwen2.5-coder:")
    ):
        return target

    return value



import concurrent.futures
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .agent_streaming import AgentStreamingMixin
from .agent_subagents import AgentSubagentsMixin
from modules.common.latency_trace import latency_trace

logger = logging.getLogger("agent.orchestrator")


class AgentTurnMixin(AgentStreamingMixin, AgentSubagentsMixin):
    """Multi-turn LLM and tool execution logic for AgentOrchestrator."""

    ollama_client: Any
    provider_client: Any
    provider_name: str
    llm_provider: str
    clm_fallback_enabled: bool
    clm_fallback_model: str
    fallback_on_missing_model: bool
    fallback_on_error: bool
    ollama_think: Any
    ollama_keep_alive: Any
    temperature: float
    num_ctx: int
    chat_num_predict: int
    max_steps: int
    subagent_max_steps: int
    subagent_workers: int
    persona_system_prompt: str
    persona_num_predict: int
    persona_stream_enabled: bool
    chat_history: List[Dict[str, Any]]
    subagent_profiles: Dict[str, Any]
    last_routed_subagents: List[str]
    tool_registry: Any
    router: Any
    progress_manager: Any
    _cached_model_names: List[str]
    _cached_model_names_ts: float

    def _chat_via_provider(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if self.provider_client is None:
            raise RuntimeError(f"Provider client not initialized for {self.llm_provider}")

        provider_messages: List[Dict[str, str]] = []
        for msg in messages:
            role = str(msg.get("role", "user"))
            content = str(msg.get("content", ""))
            if role == "assistant" and not content.strip() and msg.get("tool_calls"):
                try:
                    calls = [
                        {
                            "tool": t.get("function", {}).get("name", ""),
                            "arguments": t.get("function", {}).get("arguments", {}),
                        }
                        for t in msg.get("tool_calls", [])
                    ]
                    content = f"[tool_call] {json.dumps(calls, ensure_ascii=False)}"
                except Exception:
                    content = "[tool_call]"
            elif role == "tool":
                tool_name = str(msg.get("name", "")).strip()
                content = f"[tool_result {tool_name}] {content}"
                role = "user"
            provider_messages.append({"role": role, "content": content})

        tool_list = tools or []
        if tool_list and provider_messages:
            tool_instruction = self._build_provider_tool_instruction(tool_list)
            if tool_instruction:
                has_system = False
                for item in provider_messages:
                    if item.get("role") == "system":
                        item["content"] = f"{item.get('content', '')}\n\n{tool_instruction}".strip()
                        has_system = True
                        break
                if not has_system:
                    provider_messages.insert(0, {"role": "system", "content": tool_instruction})

        res = self.provider_client.chat(
            messages=provider_messages,
            model=model or self.provider_client.model,
            options=options,
        )
        text = str(res.get("text", "")).strip()
        parsed_call = self._parse_provider_tool_call(text, tool_list) if tool_list else None
        if parsed_call:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": parsed_call["name"],
                                "arguments": parsed_call["arguments"],
                            }
                        }
                    ],
                }
            }
        return {"message": {"role": "assistant", "content": text}}

    def _chat_turn(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        model = _sentrybot_normalize_agent_turn_model(model)
        if self.llm_provider != "ollama":
            try:
                return self._chat_via_provider(model, messages, tools, options)
            except Exception as exc:
                if not self.fallback_on_error:
                    raise
                logger.warning("Primary provider %s failed (%s), falling back to Ollama", self.llm_provider, exc)

        runtime_model = self._pick_runtime_model(model)
        kwargs: Dict[str, Any] = {
            "model": runtime_model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if options:
            kwargs["options"] = options
        ollama_think = getattr(self, "ollama_think", None)
        if ollama_think is not None:
            kwargs["think"] = ollama_think
        ollama_keep_alive = getattr(self, "ollama_keep_alive", None)
        if ollama_keep_alive is not None:
            kwargs["keep_alive"] = ollama_keep_alive
        kwargs["priority"] = 0  # Interactive user turn preempts background tasks
        try:
            return self.ollama_client.chat(**kwargs)
        except Exception as exc:
            fallback = str(self.clm_fallback_model or "").strip()
            if (
                self.clm_fallback_enabled
                and self.fallback_on_error
                and fallback
                and runtime_model != fallback
            ):
                logger.warning("Ollama call failed with '%s' (%s). Retrying with fallback '%s'.", runtime_model, exc, fallback)
                kwargs["model"] = fallback
                return self.ollama_client.chat(**kwargs)
            raise

    def _run_native_history_loop(
        self,
        active_model: str,
        messages: List[Dict[str, Any]],
        actions_out: Optional[List[Dict[str, Any]]] = None,
        num_predict: Optional[int] = None,
        on_sentence: Optional[Callable[[str, int], None]] = None,
        max_steps: int = 4,
        trace_id: Optional[str] = None,
    ) -> Tuple[str, int]:
        def _as_dict(value: Any) -> Dict[str, Any]:
            if isinstance(value, dict):
                return value
            if hasattr(value, "model_dump"):
                try:
                    dumped = value.model_dump()
                    return dumped if isinstance(dumped, dict) else {}
                except Exception:
                    return {}
            if hasattr(value, "dict"):
                try:
                    dumped = value.dict()
                    return dumped if isinstance(dumped, dict) else {}
                except Exception:
                    return {}
            try:
                dumped = dict(value)
                return dumped if isinstance(dumped, dict) else {}
            except Exception:
                return {}

        def _normalize_args(raw_args: Any) -> Dict[str, Any]:
            if isinstance(raw_args, dict):
                return raw_args
            if isinstance(raw_args, str):
                raw_args = raw_args.strip()
                if not raw_args:
                    return {}
                try:
                    parsed = json.loads(raw_args)
                    return parsed if isinstance(parsed, dict) else {}
                except Exception:
                    logger.warning("Could not parse tool arguments as JSON: %s", raw_args[:200])
                    return {}
            return {}

        def _normalize_tool_calls(raw_calls: Any) -> List[Dict[str, Any]]:
            if not raw_calls:
                return []
            normalized: List[Dict[str, Any]] = []
            for raw_call in raw_calls:
                call = _as_dict(raw_call)
                function = _as_dict(call.get("function", {}))
                if not function and hasattr(raw_call, "function"):
                    function = _as_dict(getattr(raw_call, "function"))
                name = str(function.get("name", "") or call.get("name", "")).strip()
                args = _normalize_args(function.get("arguments", call.get("arguments", {})))
                if not name:
                    continue
                normalized.append({"function": {"name": name, "arguments": args}})
            return normalized

        tools = self.tool_registry.get_tool_schema()
        options: Dict[str, Any] = {
            "temperature": self.temperature,
            "num_predict": num_predict or self.chat_num_predict,
            "num_ctx": self.num_ctx,
        }
        executed = actions_out if actions_out is not None else []
        step_count = 0
        final_content = ""

        while step_count < max_steps:
            step_count += 1
            res = self._chat_maybe_stream(
                active_model,
                messages,
                tools,
                options,
                on_sentence=on_sentence,
            )
            res_dict = _as_dict(res)
            msg = _as_dict(res_dict.get("message", {}))
            if not msg and hasattr(res, "message"):
                msg = _as_dict(getattr(res, "message"))
            content = str(msg.get("content", "") or "")
            tool_calls = _normalize_tool_calls(msg.get("tool_calls", []))

            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if not tool_calls:
                final_content = content
                break

            for call in tool_calls:
                fn = call.get("function", {})
                name = str(fn.get("name", "") or "").strip()
                args = _normalize_args(fn.get("arguments", {}))
                if not name:
                    continue

                out = self.tool_registry.execute(name, args)
                executed.append({"tool": name, "args": args, "result": out})

                messages.append({
                    "role": "tool",
                    "name": name,
                    "content": json.dumps(out, ensure_ascii=False) if isinstance(out, (dict, list)) else str(out),
                })

        return final_content, step_count

    def _step_internal(
        self,
        user_prompt: str,
        system_override: Optional[str] = None,
        max_steps: Optional[int] = None,
        on_sentence: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        t0 = time.time()
        latency_trace.reset()
        limit = max_steps or self.max_steps
        executed_actions: List[Dict[str, Any]] = []

        if self.router.is_tri_layer_enabled():
            final_text, steps, sub_results = self._run_tri_layer(
                user_prompt, "", None, self.model, "en", "", None, on_sentence=on_sentence
            )
            return {
                "ok": True,
                "text": final_text,
                "actions": [],
                "steps": steps,
                "mode": "tri_layer",
                "subagents": [r.get("name") for r in sub_results],
            }

        messages = self.build_context(user_prompt, system_override=system_override)
        final_content, step_count = self._run_native_history_loop(
            self.model,
            messages,
            actions_out=executed_actions,
            max_steps=limit,
            on_sentence=on_sentence,
        )

        duration_ms = int((time.time() - t0) * 1000)
        self.chat_history.append({"role": "user", "content": user_prompt})
        self.chat_history.append({"role": "assistant", "content": final_content})

        return {
            "ok": True,
            "text": final_content,
            "actions": executed_actions,
            "steps": step_count,
            "duration_ms": duration_ms,
        }
