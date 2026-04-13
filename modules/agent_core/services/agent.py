import logging
import os
import time
import json
from typing import Any, Dict, List, Optional, Tuple

from .world_state import WorldState
from .memory import EpisodicMemory
from .slam import TopologicalMap
from .tools import ToolRegistry
from .safety_filter import ActionSafetyFilter
from .sensor_loop import SensorFeedbackLoop
from .idle_behavior import IdleBehaviorSystem
from .tri_layer import SubAgentProfile, TriLayerRouter, build_subagent_profiles

logger = logging.getLogger("agent.orchestrator")

# If ollama library is available.
try:
    import ollama
except ImportError:
    ollama = None

try:
    from modules.ollama.services.clients import create_llm_client  # type: ignore
    from modules.ollama.config_loader import load_config as load_ollama_runtime_config  # type: ignore
except Exception:
    create_llm_client = None  # type: ignore
    load_ollama_runtime_config = None  # type: ignore


class AgentOrchestrator:
    """
    SentryBOT's Embodied AI - Native Tool Calling Edition.
    Runs an autonomous loop up to MAX_STEPS allowing unrestricted
    tool use (e.g. database search -> look around -> move head) in one reasoning pass.
    """

    def __init__(self, config: dict, autonomy_client=None):
        """
        Args:
            config: The agent.yaml config dict.
            autonomy_client: ServiceClient used to trigger real hardware.
        """
        self.config = config
        self.autonomy_client = autonomy_client

        # LLM settings
        agent_cfg = config.get("agent", {})
        self.model = agent_cfg.get("model", "llama3.2:3b-q4_K_M")
        self.temperature = agent_cfg.get("temperature", 0.15)
        self.num_ctx = agent_cfg.get("num_ctx", 4096)
        self.cooldown = agent_cfg.get("cooldown_s", 1.0)
        llm_cfg = config.get("llm", {}) if isinstance(config.get("llm", {}), dict) else {}
        self.llm_provider = str(llm_cfg.get("provider", "ollama")).strip().lower() or "ollama"
        self.clm_fallback_enabled = bool(llm_cfg.get("clm_fallback_enabled", True))
        self.clm_fallback_model = str(
            llm_cfg.get("clm_fallback_model", agent_cfg.get("clm_fallback_model", ""))
        ).strip()
        self.fallback_on_missing_model = bool(llm_cfg.get("fallback_on_missing_model", True))
        self.fallback_on_error = bool(llm_cfg.get("fallback_on_error", True))
        self.request_timeout = self._safe_float(
            agent_cfg.get("request_timeout", agent_cfg.get("ollama_request_timeout", 60.0)),
            fallback=60.0,
            minimum=1.0,
        )
        self.max_steps = self._safe_int(
            agent_cfg.get("max_steps", agent_cfg.get("max_tool_loops", 10)),
            fallback=10,
            minimum=1,
        )
        self.ollama_base_url = self._resolve_ollama_base_url(agent_cfg)

        if self.llm_provider != "ollama":
            logger.info(
                "Agent Core running in provider mode: %s (limited tool-calling adaptation enabled)",
                self.llm_provider,
            )

        self.ollama_client = None
        self.provider_client = None
        self.provider_name = self.llm_provider
        self._cached_model_names: List[str] = []
        self._cached_model_names_ts = 0.0

        if ollama:
            try:
                self.ollama_client = ollama.Client(host=self.ollama_base_url, timeout=self.request_timeout)
            except Exception as exc:
                logger.warning("Ollama client init failed for host %s: %s", self.ollama_base_url, exc)
                try:
                    self.ollama_client = ollama.Client(host=self.ollama_base_url)
                except Exception:
                    self.ollama_client = None

        if self.llm_provider != "ollama" and create_llm_client and load_ollama_runtime_config:
            try:
                runtime_cfg = load_ollama_runtime_config(None)
                if isinstance(runtime_cfg, dict):
                    runtime_cfg.setdefault("llm", {})["provider"] = self.llm_provider
                self.provider_client, self.provider_name = create_llm_client(runtime_cfg)
            except Exception as exc:
                logger.warning("Provider client init failed for provider %s: %s", self.llm_provider, exc)

        # Subsystems
        self.world_state = WorldState()
        self.memory = EpisodicMemory()
        self.slam = TopologicalMap()
        self.safety_filter = ActionSafetyFilter(config)
        self.tool_registry = ToolRegistry(
            client=self.autonomy_client,
            memory=self.memory,
            slam=self.slam,
            world_state=self.world_state,
            safety_filter=self.safety_filter
        )

        # Background threads
        self.sensor_loop = SensorFeedbackLoop(self.world_state, client=autonomy_client)
        self.idle_system = IdleBehaviorSystem(self, client=autonomy_client)

        self.last_run = 0.0
        self.is_busy = False

        # Short-term conversational/reasoning memory across steps
        self.chat_history = []
        self.max_history = agent_cfg.get("max_history", 10)

        # MARK: Tri-layer agent settings (router -> sub-agents -> main persona)
        tri_cfg = self.config.get("tri_layer", {}) if isinstance(self.config.get("tri_layer", {}), dict) else {}
        router_cfg = tri_cfg.get("router", {}) if isinstance(tri_cfg.get("router", {}), dict) else {}
        subagent_cfg = tri_cfg.get("subagent", {}) if isinstance(tri_cfg.get("subagent", {}), dict) else {}
        persona_cfg = tri_cfg.get("persona", {}) if isinstance(tri_cfg.get("persona", {}), dict) else {}

        default_modules = router_cfg.get("default_modules", ["autonomy", "agent_core"])
        if not isinstance(default_modules, list):
            default_modules = ["autonomy", "agent_core"]

        profile_overrides = tri_cfg.get("profiles") if isinstance(tri_cfg.get("profiles"), dict) else None
        self.subagent_profiles = build_subagent_profiles(profile_overrides)
        self.router = TriLayerRouter(
            profiles=self.subagent_profiles,
            max_subagents=self._safe_int(router_cfg.get("max_subagents", 2), fallback=2, minimum=1),
            default_modules=default_modules,
        )

        self.tri_layer_enabled = bool(tri_cfg.get("enabled", True))
        self.subagent_max_steps = self._safe_int(subagent_cfg.get("max_steps", 2), fallback=2, minimum=1)
        self.persona_num_predict = self._safe_int(persona_cfg.get("num_predict", 220), fallback=220, minimum=64)
        self.last_routed_subagents: List[str] = []

    @staticmethod
    def _safe_int(value: Any, fallback: int, minimum: int = 1) -> int:
        try:
            return max(minimum, int(value))
        except (TypeError, ValueError):
            return max(minimum, int(fallback))

    @staticmethod
    def _safe_float(value: Any, fallback: float, minimum: float = 0.0) -> float:
        try:
            return max(minimum, float(value))
        except (TypeError, ValueError):
            return max(minimum, float(fallback))

    def start(self):
        """Start background subsystems."""
        self.sensor_loop.start()
        self.idle_system.start()
        logger.info("AgentOrchestrator subsystems started.")

    def stop(self):
        self.sensor_loop.stop()
        self.idle_system.stop()
        logger.info("AgentOrchestrator subsystems stopped.")

    def check_survival_drives(self):
        """Overrides logic if critical limits are reached."""
        bat = self.world_state.get_state().get("battery_percent", 100)
        if bat < 15:
            logger.warning("SURVIVAL DRIVE: Low Battery (%s%%)!", bat)
            return "[CRITICAL] Battery is severely low. Do not engage in lengthy tasks. Find a charger or warn the user."
        return None

    def _append_history(self, role: str, content: str, tool_calls=None, tool_name=None):
        msg = {"role": role, "content": content}
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_name is not None:
            msg["name"] = tool_name

        self.chat_history.append(msg)
        # Keep last N * 2 turns
        limit = self.max_history * 2
        if len(self.chat_history) > limit:
            self.chat_history = self.chat_history[-limit:]

    def route_preview(self, user_prompt: str) -> Dict[str, Any]:
        modules = self.router.route(user_prompt)
        return {
            "enabled": self.tri_layer_enabled,
            "modules": modules,
            "available": sorted(self.subagent_profiles.keys()),
        }

    def _get_active_persona_model(self) -> str:
        """Resolve the model for the native tool loop."""
        llm_model = str(self.config.get("llm", {}).get("model", "")).strip()
        if llm_model:
            return llm_model
        return str(self.model)

    def _resolve_ollama_base_url(self, agent_cfg: Dict[str, Any]) -> str:
        llm_cfg = self.config.get("llm", {}) or {}
        value = (
            llm_cfg.get("base_url")
            or agent_cfg.get("ollama_base_url")
            or os.getenv("AGENT_OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_HOST")
            or "http://127.0.0.1:11434"
        )
        return str(value).strip().rstrip("/")

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        text = str(content or "").strip()
        if text.startswith("```") and text.endswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return text

    def _build_provider_tool_instruction(self, tools: List[Dict[str, Any]]) -> str:
        names = [str(t.get("function", {}).get("name", "")).strip() for t in tools]
        names = [n for n in names if n]
        if not names:
            return ""
        joined = ", ".join(names)
        return (
            "You may choose at most one tool from this list: "
            f"{joined}. "
            "If a tool is required, reply with ONLY strict JSON: "
            '{"tool":"tool_name","arguments":{...}}. '
            "If no tool is needed, reply with plain text only."
        )

    def _parse_provider_tool_call(self, content: str, tools: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not content or not tools:
            return None

        allowed = {
            str(t.get("function", {}).get("name", "")).strip()
            for t in tools
            if str(t.get("function", {}).get("name", "")).strip()
        }
        cleaned = self._strip_code_fence(content)
        try:
            data = json.loads(cleaned)
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        tool_name = str(data.get("tool", "")).strip()
        if tool_name not in allowed:
            return None

        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}

        return {
            "function": {
                "name": tool_name,
                "arguments": arguments,
            }
        }

    def _list_ollama_models(self) -> List[str]:
        now = time.time()
        if now - self._cached_model_names_ts < 30.0 and self._cached_model_names:
            return list(self._cached_model_names)

        names: List[str] = []
        if self.ollama_client is not None and hasattr(self.ollama_client, "list"):
            try:
                raw = self.ollama_client.list()  # type: ignore[attr-defined]
                items = raw.get("models", []) if isinstance(raw, dict) else []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    if name:
                        names.append(name)
            except Exception:
                names = []

        self._cached_model_names = names
        self._cached_model_names_ts = now
        return list(names)

    def _pick_runtime_model(self, preferred_model: str) -> str:
        model = str(preferred_model or "").strip()
        if self.llm_provider != "ollama":
            return model

        if not self.clm_fallback_enabled or not self.fallback_on_missing_model:
            return model

        fallback = str(self.clm_fallback_model or "").strip()
        if not model or not fallback or fallback == model:
            return model

        available = self._list_ollama_models()
        if available and model not in available and fallback in available:
            logger.warning("Primary model '%s' is missing. Switching to fallback '%s'.", model, fallback)
            return fallback
        return model

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
            provider_messages.append({"role": role, "content": content})

        tool_list = tools or []
        if tool_list and provider_messages:
            tool_instruction = self._build_provider_tool_instruction(tool_list)
            if tool_instruction:
                provider_messages[-1] = {
                    "role": provider_messages[-1]["role"],
                    "content": f"{provider_messages[-1]['content']}\n\n{tool_instruction}",
                }

        response = self.provider_client.chat(
            messages=provider_messages,
            options=options,
            model=model or None,
        )
        content = str(response.get("message", {}).get("content", "")).strip()

        parsed_tool = self._parse_provider_tool_call(content, tool_list)
        if parsed_tool is not None:
            return {
                "message": {
                    "content": "",
                    "tool_calls": [parsed_tool],
                }
            }
        return {"message": {"content": content}}

    def _chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if options is not None:
            kwargs["options"] = options

        selected_model = self._pick_runtime_model(model)
        kwargs["model"] = selected_model

        if self.llm_provider != "ollama":
            return self._chat_via_provider(selected_model, messages, tools, options)

        try:
            if self.ollama_client is not None:
                return self.ollama_client.chat(**kwargs)
            return ollama.chat(**kwargs)
        except Exception as exc:
            fallback = str(self.clm_fallback_model or "").strip()
            if (
                self.clm_fallback_enabled
                and self.fallback_on_error
                and fallback
                and fallback != selected_model
            ):
                logger.warning(
                    "Primary model '%s' failed (%s). Retrying with fallback '%s'.",
                    selected_model,
                    exc,
                    fallback,
                )
                kwargs["model"] = fallback
                if self.ollama_client is not None:
                    return self.ollama_client.chat(**kwargs)
                return ollama.chat(**kwargs)
            raise

    @staticmethod
    def _extract_tool_arguments(raw_arguments: Any) -> Dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str) and raw_arguments.strip():
            try:
                parsed = json.loads(raw_arguments)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    def _run_native_history_loop(self, active_model: str, messages: List[Dict[str, Any]]) -> Tuple[str, int]:
        tools = self.tool_registry.get_tool_schema()
        final_text = ""
        step_idx = 0

        for step_idx in range(self.max_steps):
            try:
                response = self._chat(
                    model=active_model,
                    messages=messages,
                    tools=tools,
                    options={
                        "temperature": self.temperature,
                        "num_ctx": self.num_ctx,
                    },
                )
            except Exception as exc:
                logger.error("LLM tool loop crashed: %s", exc)
                final_text = "System fault during cognitive cycle."
                break

            msg = response.get("message", {})
            messages.append(msg)

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                log_tc = [
                    {
                        "name": t.get("function", {}).get("name"),
                        "args": t.get("function", {}).get("arguments"),
                    }
                    for t in tool_calls
                ]
                logger.info("Agent Loop [%s/%s] Using tools: %s", step_idx + 1, self.max_steps, log_tc)
                self._append_history("assistant", msg.get("content", ""), tool_calls=tool_calls)

                for tool in tool_calls:
                    fn_name = str(tool.get("function", {}).get("name", ""))
                    fn_args = self._extract_tool_arguments(tool.get("function", {}).get("arguments", {}))

                    tool_result_str = self.tool_registry.execute(fn_name, fn_args)
                    tool_msg = {
                        "role": "tool",
                        "content": tool_result_str,
                        "name": fn_name,
                    }
                    messages.append(tool_msg)
                    self._append_history("tool", tool_result_str, tool_name=fn_name)
                continue

            final_text = str(msg.get("content", ""))
            self._append_history("assistant", final_text)
            logger.info("Agent Final Response: %s", final_text)
            break

        if not final_text:
            final_text = "Task completed using internal tools."

        return final_text, step_idx + 1

    def _run_subagent(
        self,
        profile: SubAgentProfile,
        user_prompt: str,
        world_context: str,
        survival_override: Optional[str],
        active_model: str,
    ) -> Dict[str, Any]:
        allowed_tools = [name for name in profile.allowed_tools if name in self.tool_registry.get_tool_names()]
        tools = self.tool_registry.get_tool_schema(include=allowed_tools)

        # MARK: Layer-2 prompt keeps each sub-agent narrow and module-focused.
        system_prompt = (
            "You are a focused module sub-agent in a tri-layer robotics system. "
            "Stay inside your module scope and keep outputs concise.\n"
            f"Module: {profile.module}\n"
            f"Role: {profile.role}\n"
            f"Goal: {profile.goal}\n"
            "Use tools only when needed. Do not roleplay as main persona."
        )

        user_payload = (
            "[Original Request]\n"
            f"{user_prompt}\n\n"
            "[World State]\n"
            f"{world_context}"
        )
        if survival_override:
            user_payload += f"\n\n[Safety Override]\n{survival_override}"

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ]

        final_text = ""
        used_tools: List[str] = []
        steps_taken = 0
        max_steps = self.subagent_max_steps if tools else 1

        for idx in range(max_steps):
            try:
                response = self._chat(
                    model=active_model,
                    messages=messages,
                    tools=tools if tools else None,
                    options={
                        "temperature": self.temperature,
                        "num_ctx": self.num_ctx,
                    },
                )
            except Exception as exc:
                logger.warning("Sub-agent '%s' failed: %s", profile.module, exc)
                final_text = "Sub-agent execution failed."
                steps_taken = idx + 1
                break

            msg = response.get("message", {})
            messages.append(msg)
            steps_taken = idx + 1

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                final_text = str(msg.get("content", "")).strip()
                break

            for tool in tool_calls:
                fn_name = str(tool.get("function", {}).get("name", ""))
                fn_args = self._extract_tool_arguments(tool.get("function", {}).get("arguments", {}))
                tool_result_str = self.tool_registry.execute(fn_name, fn_args)
                used_tools.append(fn_name)
                messages.append(
                    {
                        "role": "tool",
                        "name": fn_name,
                        "content": tool_result_str,
                    }
                )

        if not final_text:
            final_text = f"Sub-agent '{profile.module}' completed."

        return {
            "module": profile.module,
            "text": final_text,
            "tools": used_tools,
            "steps": steps_taken,
        }

    def _synthesize_main_persona(
        self,
        user_prompt: str,
        reports: List[Dict[str, Any]],
        survival_override: Optional[str],
        active_model: str,
    ) -> str:
        # MARK: Layer-3 is the only layer that speaks as the main persona.
        system_prompt = (
            "You are SentryBOT main persona and final response layer. "
            "Combine sub-agent findings into one direct answer for the user. "
            "Do not expose internal chain details unless the user explicitly asks. "
            "Prioritize safety constraints when present."
        )

        user_payload = {
            "request": user_prompt,
            "safety_override": survival_override or "",
            "subagent_reports": reports,
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ]

        try:
            response = self._chat(
                model=active_model,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.persona_num_predict,
                },
            )
            final_text = str(response.get("message", {}).get("content", "")).strip()
            if final_text:
                return final_text
        except Exception as exc:
            logger.warning("Main persona synthesis failed: %s", exc)

        if reports:
            return str(reports[0].get("text", ""))
        return "Task completed using internal tools."

    def step(self, user_prompt: str = "") -> Optional[Dict[str, Any]]:
        """
        One complete Agent thought cycle.
        Executes a multi-stage tool-calling loop (max N steps).
        """
        now = time.time()
        if now - self.last_run < self.cooldown:
            return None
        self.last_run = now

        if self.is_busy or not user_prompt:
            return None

        self.is_busy = True

        try:
            # 1. Collect world & survival context
            survival_override = self.check_survival_drives()
            world_context = self.world_state.inject_world_state("")

            full_prompt = f"{user_prompt}\n\n[World State]\n{world_context}"
            if survival_override:
                full_prompt += f"\n\n{survival_override}"

            self._append_history("user", full_prompt)
            active_model = self._get_active_persona_model()

            if self.llm_provider == "ollama" and not ollama:
                logger.error("Ollama library not found. Native tool loop requires 'ollama' package.")
                return {"text": "System Error: Missing ollama backend."}

            if self.llm_provider != "ollama" and self.provider_client is None:
                logger.error("Provider '%s' selected but provider client is unavailable.", self.llm_provider)
                return {"text": "System Error: Missing provider client backend."}

            final_text = ""
            total_steps = 0
            subagent_reports: List[Dict[str, Any]] = []

            if self.tri_layer_enabled:
                self.last_routed_subagents = self.router.route(user_prompt)
                logger.info("Tri-layer route selected: %s", self.last_routed_subagents)

                for module_name in self.last_routed_subagents:
                    profile = self.subagent_profiles.get(module_name)
                    if not profile:
                        continue
                    report = self._run_subagent(
                        profile=profile,
                        user_prompt=user_prompt,
                        world_context=world_context,
                        survival_override=survival_override,
                        active_model=active_model,
                    )
                    subagent_reports.append(report)
                    total_steps += int(report.get("steps", 0))

                if subagent_reports:
                    final_text = self._synthesize_main_persona(
                        user_prompt=user_prompt,
                        reports=subagent_reports,
                        survival_override=survival_override,
                        active_model=active_model,
                    )
                    self._append_history("assistant", final_text)
                else:
                    messages = list(self.chat_history)
                    final_text, total_steps = self._run_native_history_loop(active_model, messages)
            else:
                messages = list(self.chat_history)
                final_text, total_steps = self._run_native_history_loop(active_model, messages)
                
            # 4. Save to episodic long-term memory
            self.memory.remember("dialogue", f"User: {user_prompt} | Bot: {final_text}")

            # 5. Return dict matching AutonomyBrain expectations (but empty plan/actions)
            return {
                "text": final_text,
                "thoughts": f"Tri-layer executed with {total_steps} internal steps.",
                "actions": [],
                "plan": [],
                "route": self.last_routed_subagents,
                "subagents": subagent_reports,
            }

        finally:
            self.is_busy = False
