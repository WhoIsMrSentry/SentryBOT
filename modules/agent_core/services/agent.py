import logging
import os
import time
import json
import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple, Callable

from .world_state import WorldState
from .memory import EpisodicMemory
from .slam import TopologicalMap
from .tools import ToolRegistry
from .safety_filter import ActionSafetyFilter
from .sensor_loop import SensorFeedbackLoop
from .idle_behavior import IdleBehaviorSystem
from .tri_layer import SubAgentProfile, TriLayerRouter, build_subagent_profiles
from .progress import ProgressManager
from .speech_arbiter import SpeechArbiter
from .action_arbiter import ActionArbiter
from .tool_execution_arbiter import ToolExecutionArbiter
from .vision_arbiter import VisionArbiter
from .expression_arbiter import ExpressionArbiter

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

        actions_cfg = config.get("actions", {}) if isinstance(config.get("actions", {}), dict) else {}
        try:
            from modules.gateway.url import resolve_config_url, resolve_gateway_base_url

            default_gw = resolve_gateway_base_url(self.config)
            raw_gw = str(actions_cfg.get("gateway_base_url", default_gw)).strip()
            self._gateway_base_url = resolve_config_url(raw_gw, default_gw).rstrip("/")
        except Exception:
            self._gateway_base_url = str(
                actions_cfg.get("gateway_base_url", "http://127.0.0.1:8080")
            ).rstrip("/")
        self._action_http_timeout_s = float(actions_cfg.get("http_timeout_s", 2.5))

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
        self.status_interval_s = self._safe_float(
            agent_cfg.get("status_interval_s", 2.0),
            fallback=2.0,
            minimum=0.2,
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

        if self.llm_provider != "ollama" and create_llm_client:
            try:
                self.provider_client, self.provider_name = create_llm_client(self.config)
                logger.info(
                    "LLM provider client ready: %s (model=%s)",
                    self.provider_name,
                    getattr(self.provider_client, "model", ""),
                )
            except Exception as exc:
                logger.error(
                    "Provider client init failed for %s: %s",
                    self.llm_provider,
                    exc,
                )

        # Subsystems
        self.world_state = WorldState()
        self.memory = EpisodicMemory()
        self.memory_consolidator = self._build_memory_consolidator()
        self.slam = TopologicalMap()
        self.safety_filter = ActionSafetyFilter(config)
        self.tool_execution_arbiter = ToolExecutionArbiter()
        # ── Living Vision Agent: Arbiter & Progress subsystems ──
        # Instantiated before ToolRegistry so vlm tools can lock the vision arbiter.
        self.action_arbiter = ActionArbiter()
        self.vision_arbiter = VisionArbiter()
        self.expression_arbiter = ExpressionArbiter()
        self.speech_arbiter = SpeechArbiter()
        self.progress_manager = ProgressManager(speech_arbiter=self.speech_arbiter)
        self.progress_manager.attach_arbiters(
            action_arbiter=self.action_arbiter,
            vision_arbiter=self.vision_arbiter,
            expression_arbiter=self.expression_arbiter,
            tool_execution_arbiter=self.tool_execution_arbiter,
        )

        self.tool_registry = ToolRegistry(
            client=self.autonomy_client,
            memory=self.memory,
            slam=self.slam,
            world_state=self.world_state,
            safety_filter=self.safety_filter,
            tool_execution_arbiter=self.tool_execution_arbiter,
            vision_arbiter=self.vision_arbiter,
            vlm_ask_timeout_s=float((config.get("tool_execution", {}) or {}).get("timeout_s", 22.0)),
            gateway_base_url=self._gateway_base_url,
        )

        # Background threads
        self.sensor_loop = SensorFeedbackLoop(self.world_state, client=autonomy_client)
        self.idle_system = IdleBehaviorSystem(self, client=autonomy_client)
        if self.autonomy_client and hasattr(self.autonomy_client, "set_stt_suppressed"):
            self.speech_arbiter.set_tts_state_callback(
                lambda active: self.autonomy_client.set_stt_suppressed(bool(active))
            )
        if self.autonomy_client and hasattr(self.autonomy_client, "stop_speaking"):
            self.speech_arbiter.set_stop_playback_fn(self.autonomy_client.stop_speaking)
        self._register_action_handlers()

        self.last_run = 0.0
        self.is_busy = False
        self._active_progress_token: str = ""

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
        if not self._camera_input_available():
            default_modules = [m for m in default_modules if str(m).strip().lower() != "vlm_bridge"]

        profile_overrides = tri_cfg.get("profiles") if isinstance(tri_cfg.get("profiles"), dict) else None
        self.subagent_profiles = build_subagent_profiles(profile_overrides)
        self.router = TriLayerRouter(
            profiles=self.subagent_profiles,
            max_subagents=self._safe_int(router_cfg.get("max_subagents", 2), fallback=2, minimum=1),
            default_modules=default_modules,
        )

        self.tri_layer_enabled = bool(tri_cfg.get("enabled", True))
        self.subagent_max_steps = self._safe_int(subagent_cfg.get("max_steps", 2), fallback=2, minimum=1)
        # Number of worker threads for running sub-agents in parallel to reduce latency
        self.subagent_workers = self._safe_int(subagent_cfg.get("workers", 2), fallback=2, minimum=1)
        # Persona system prompt can be overridden via config.tri_layer.persona.system_prompt
        self.persona_system_prompt = str(persona_cfg.get("system_prompt", "")).strip()
        default_persona_np = persona_cfg.get("num_predict", 180)
        self.persona_num_predict = self._safe_int(default_persona_np, fallback=180, minimum=64)
        self.chat_num_predict = self._safe_int(agent_cfg.get("num_predict", 100), fallback=100, minimum=48)

        # Apply active realtime profile overrides at startup
        rt_cfg = self.config.get("realtime_profile", {}) if isinstance(self.config.get("realtime_profile", {}), dict) else {}
        active_profile_name = str(rt_cfg.get("active", "")).strip().lower()
        profiles_map = rt_cfg.get("profiles", {}) if isinstance(rt_cfg.get("profiles", {}), dict) else {}
        active_profile = profiles_map.get(active_profile_name, {}) if active_profile_name else {}
        if not isinstance(active_profile, dict) or not active_profile:
            active_profile = rt_cfg.get(active_profile_name, {}) if active_profile_name else {}
        if isinstance(active_profile, dict) and active_profile:
            self.apply_realtime_profile(active_profile)

        self.last_routed_subagents: List[str] = []

    def _build_memory_consolidator(self):
        """Wire the consolidator to episodic memory and (if present) social_db.

        This is the bridge that lets durable facts mined from dialogue land in
        both the episodic store and the speaker's social record.
        """
        from .memory_consolidator import MemoryConsolidator

        social_db = None
        try:
            from modules.social_db import get_default as _social_default  # type: ignore

            social_db = _social_default()
        except Exception:
            social_db = None
        return MemoryConsolidator(memory=self.memory, social_db=social_db)

    def _current_speaker(self):
        """Best-effort identity of who is currently talking (or None)."""
        try:
            state = getattr(self.world_state, "state", {}) or {}
            speaker = state.get("speaker") or state.get("current_person")
            if speaker and str(speaker).strip().lower() not in {"unknown", "none"}:
                return str(speaker).strip()
        except Exception:
            pass
        return None

    def _register_action_handlers(self) -> None:
        """Bind ActionArbiter actions to concrete side effects.

        ``head_move`` and the vision-oriented action types are routed through
        the VLM bridge HTTP surface so the unified :class:`HeadControlArbiter`
        and :class:`VisionArbiter` arbitrate every request.
        """
        def _handle_speak(req):
            text = str(req.payload.get("text", "")).strip()
            if not text:
                return {"ok": False, "reason": "missing_text"}
            # Forward the emotional tone so prosody survives the queue hop;
            # previously it was dropped here, flattening every utterance.
            tone = req.payload.get("tone")
            if not isinstance(tone, (dict, str)) or tone == "":
                tone = None
            self.speech_arbiter.enqueue(
                text=text,
                priority=max(1, min(100, int(req.priority))),
                category="final" if req.priority >= 60 else "progress",
                language=str(req.payload.get("language", "") or ""),
                tone=tone,
            )
            return {"ok": True}

        def _http_post(path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            try:
                import requests  # type: ignore
            except Exception as exc:
                return {"ok": False, "reason": "no_requests", "error": str(exc)}
            url = f"{self._gateway_base_url}{path}"
            try:
                resp = requests.post(
                    url,
                    json=payload or {},
                    timeout=self._action_http_timeout_s,
                )
                if resp.status_code != 200:
                    return {"ok": False, "reason": "http_error", "status": resp.status_code}
                try:
                    return {"ok": True, "data": resp.json()}
                except Exception:
                    return {"ok": True, "data": {}}
            except Exception as exc:
                return {"ok": False, "reason": "http_exception", "error": str(exc)}

        def _handle_head(req):
            pan = self.safety_filter.clamp_servo(int(req.payload.get("pan", 90)))
            tilt = self.safety_filter.clamp_servo(int(req.payload.get("tilt", 90)))
            drive = int(req.payload.get("drive", 0) or 0)
            return _http_post(
                "/vlm/track",
                {"head_pan": pan, "head_tilt": tilt, "drive": drive},
            )

        def _handle_lights(req):
            if not self.autonomy_client:
                return {"ok": False, "reason": "no_client"}
            if not self.expression_arbiter.claim_lights(req.source, force=req.priority >= 90):
                return {"ok": False, "reason": "lights_locked"}
            try:
                effect = str(req.payload.get("effect", "BREATHE"))
                color = req.payload.get("color")
                return self.autonomy_client.set_neopixel(effect, color=color if isinstance(color, list) else None)
            finally:
                self.expression_arbiter.release(req.source)

        def _handle_vision_query(req):
            question = str(req.payload.get("question", "")).strip()
            if not question:
                return {"ok": False, "reason": "missing_question"}
            return _http_post("/vlm/ask", {"question": question})

        def _handle_follow_owner(req):
            return _http_post("/vlm/follow/owner/start", {})

        def _handle_stop_follow(req):
            return _http_post("/vlm/follow/stop", {})

        def _handle_look_around(req):
            steps = req.payload.get("steps") if isinstance(req.payload, dict) else None
            if not isinstance(steps, list) or not steps:
                steps = [(60, 90), (90, 90), (120, 90), (90, 90)]
            last: Dict[str, Any] = {}
            for entry in steps:
                if isinstance(entry, dict):
                    pan = entry.get("pan", 90)
                    tilt = entry.get("tilt", 90)
                else:
                    try:
                        pan, tilt = entry
                    except Exception:
                        continue
                last = _http_post(
                    "/vlm/track",
                    {
                        "head_pan": self.safety_filter.clamp_servo(int(pan or 90)),
                        "head_tilt": self.safety_filter.clamp_servo(int(tilt or 90)),
                    },
                )
            return last

        def _handle_face_focus(req):
            name = str(req.payload.get("name", "")).strip()
            if not name:
                return {"ok": False, "reason": "missing_name"}
            return _http_post("/vlm/focus/person", {"name": name})

        def _handle_face_register(req):
            name = str(req.payload.get("name", "")).strip()
            relationship = str(req.payload.get("relationship", "known")).strip() or "known"
            level = int(req.payload.get("recognition_level", 2) or 2)
            if not name:
                return {"ok": False, "reason": "missing_name"}
            return _http_post(
                "/vlm/person/remember",
                {"name": name, "relationship": relationship, "recognition_level": level},
            )

        self.action_arbiter.register_handler("speak", _handle_speak)
        self.action_arbiter.register_handler("head_move", _handle_head)
        self.action_arbiter.register_handler("lights", _handle_lights)
        self.action_arbiter.register_handler("vision_query", _handle_vision_query)
        self.action_arbiter.register_handler("follow_owner", _handle_follow_owner)
        self.action_arbiter.register_handler("stop_follow", _handle_stop_follow)
        self.action_arbiter.register_handler("look_around", _handle_look_around)
        self.action_arbiter.register_handler("face_focus", _handle_face_focus)
        self.action_arbiter.register_handler("face_register", _handle_face_register)

    def apply_realtime_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Apply runtime-safe realtime profile values without restart.

        Supports atomic swaps for chat/persona ``num_predict``, context window,
        temperature, request timeout, sub-agent fan-out (``max_subagents``) and
        the sub-agent worker pool size.
        """
        if not isinstance(profile, dict):
            return {}

        applied: Dict[str, Any] = {}
        if "num_predict_persona" in profile:
            self.persona_num_predict = self._safe_int(profile.get("num_predict_persona"), fallback=self.persona_num_predict, minimum=64)
            applied["num_predict_persona"] = self.persona_num_predict
        if "num_predict_chat" in profile:
            self.chat_num_predict = self._safe_int(profile.get("num_predict_chat"), fallback=self.chat_num_predict, minimum=48)
            applied["num_predict_chat"] = self.chat_num_predict
        if "num_ctx" in profile:
            self.num_ctx = self._safe_int(profile.get("num_ctx"), fallback=self.num_ctx, minimum=512)
            applied["num_ctx"] = self.num_ctx
        if "temperature" in profile:
            self.temperature = self._safe_float(profile.get("temperature"), fallback=self.temperature, minimum=0.0)
            applied["temperature"] = self.temperature
        if "request_timeout_s" in profile:
            self.request_timeout = self._safe_float(profile.get("request_timeout_s"), fallback=self.request_timeout, minimum=1.0)
            applied["request_timeout_s"] = self.request_timeout
        if "max_subagents" in profile:
            value = self._safe_int(profile.get("max_subagents"), fallback=getattr(self.router, "max_subagents", 2), minimum=1)
            if hasattr(self.router, "set_max"):
                applied["max_subagents"] = self.router.set_max(value)
            else:
                self.router.max_subagents = value
                applied["max_subagents"] = self.router.max_subagents
        if "subagent_workers" in profile:
            self.subagent_workers = self._safe_int(profile.get("subagent_workers"), fallback=self.subagent_workers, minimum=1)
            applied["subagent_workers"] = self.subagent_workers
        if "subagent_max_steps" in profile:
            self.subagent_max_steps = self._safe_int(profile.get("subagent_max_steps"), fallback=self.subagent_max_steps, minimum=1)
            applied["subagent_max_steps"] = self.subagent_max_steps

        # Keep tool VLM ask timeout aligned with active profile.
        if hasattr(self, "tool_registry") and self.tool_registry is not None:
            vlm_timeout = profile.get("vlm_ask_timeout_s", profile.get("request_timeout_s"))
            if vlm_timeout is not None:
                try:
                    self.tool_registry.vlm_ask_timeout_s = self._safe_float(vlm_timeout, fallback=self.tool_registry.vlm_ask_timeout_s, minimum=2.0)
                    applied["vlm_ask_timeout_s"] = self.tool_registry.vlm_ask_timeout_s
                except Exception:
                    pass

        # Refresh ollama client timeout for subsequent chat calls.
        if ollama:
            try:
                self.ollama_client = ollama.Client(host=self.ollama_base_url, timeout=self.request_timeout)
            except Exception:
                pass

        # Propagate low-latency chat timeout to autonomy ServiceClient, if present.
        if self.autonomy_client is not None and hasattr(self.autonomy_client, "request_timeouts"):
            chat_timeout = profile.get("ollama_chat_timeout_s")
            if chat_timeout is not None:
                try:
                    self.autonomy_client.request_timeouts["ollama_chat_s"] = float(chat_timeout)
                    applied["ollama_chat_timeout_s"] = float(chat_timeout)
                except Exception:
                    pass

        return applied

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
        self.speech_arbiter.start()
        logger.info("AgentOrchestrator subsystems started.")

    def stop(self):
        self.sensor_loop.stop()
        self.idle_system.stop()
        self.speech_arbiter.stop()
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

    @staticmethod
    def _emit_progress(progress_cb: Optional[Callable[[Dict[str, Any]], None]], payload: Dict[str, Any]) -> None:
        if not progress_cb:
            return
        try:
            progress_cb(payload)
        except Exception:
            pass

    @staticmethod
    def _safe_log_warning(message: str, *args: Any) -> None:
        try:
            logger.warning(message, *args)
        except Exception:
            pass

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

    def _build_plan_summary(self, user_prompt: str, modules: List[str]) -> List[Dict[str, str]]:
        """Build a small planner summary describing which modules will run and why.

        This is a lightweight, non-LLM plan exposed to callers so planner output
        is available immediately before longer reasoning runs.
        """
        plan: List[Dict[str, str]] = []
        for m in modules:
            profile = self.subagent_profiles.get(m)
            if profile:
                plan.append({
                    "module": m,
                    "goal": profile.goal,
                })
            else:
                plan.append({"module": m, "goal": "Execute domain-specific reasoning."})
        return plan

    def _camera_input_available(self) -> bool:
        try:
            from modules.gateway.url import gateway_url, resolve_gateway_base_url

            base = resolve_gateway_base_url()
            import requests

            resp = requests.get(gateway_url(base, "/camera/healthz"), timeout=0.35)
            if resp.status_code != 200:
                return False
            data = resp.json() if resp.content else {}
            return bool((data or {}).get("ok", False))
        except Exception:
            return False

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
            if self.provider_client is None:
                raise RuntimeError(
                    f"Provider '{self.llm_provider}' selected but client is not initialized"
                )
            return self._chat_via_provider(selected_model, messages, tools, options)

        if self.ollama_client is None and ollama is None:
            raise RuntimeError("Ollama provider selected but ollama client is unavailable")

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
                        "num_predict": self.chat_num_predict,
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
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        self._emit_progress(
            progress_cb,
            {"type": "subagent_start", "module": profile.module, "role": profile.role},
        )
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

        try:
            from modules.ollama.services.clients import GoogleAIStudioClient  # type: ignore

            if GoogleAIStudioClient.is_rate_limited(
                str(getattr(self.provider_client, "api_key", ""))
            ):
                return {
                    "module": profile.module,
                    "text": "Sub-agent skipped (LLM rate limit cooldown).",
                    "tools": [],
                    "steps": 0,
                }
        except Exception:
            pass

        for idx in range(max_steps):
            try:
                response = self._chat(
                    model=active_model,
                    messages=messages,
                    tools=tools if tools else None,
                    options={
                        "temperature": self.temperature,
                        "num_ctx": self.num_ctx,
                        "num_predict": self.chat_num_predict,
                    },
                )
            except Exception as exc:
                self._safe_log_warning("Sub-agent '%s' failed: %s", profile.module, exc)
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

        self._emit_progress(
            progress_cb,
            {"type": "subagent_done", "module": profile.module, "steps": steps_taken},
        )

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
        session_language: Optional[str] = None,
    ) -> str:
        # MARK: Layer-3 is the only layer that speaks as the main persona.
        # Use configurable persona system prompt when provided; otherwise use a neutral default
        lang_rule = self._language_directive(session_language)
        if self.persona_system_prompt:
            system_prompt = f"{self.persona_system_prompt}\n\n{lang_rule}"
        else:
            system_prompt = (
                "You are the final response layer. Combine sub-agent findings into one direct answer for the user. "
                "Do not expose internal chain details unless the user explicitly asks. "
                "Prioritize safety constraints when present.\n\n"
                f"{lang_rule}"
            )

        compact_reports = self._compact_subagent_reports(reports)
        user_payload = {
            "request": user_prompt,
            "safety_override": survival_override or "",
            "subagent_reports": compact_reports,
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ]
        adaptive_persona_np = self._adaptive_persona_num_predict(user_prompt=user_prompt, report_count=len(compact_reports))

        try:
            response = self._chat(
                model=active_model,
                messages=messages,
                options={
                    "temperature": self.temperature,
                    "num_ctx": self.num_ctx,
                    "num_predict": adaptive_persona_np,
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

    def _compact_subagent_reports(self, reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        compact: List[Dict[str, Any]] = []
        for r in reports:
            if not isinstance(r, dict):
                continue
            text = str(r.get("text", "")).strip()
            compact.append(
                {
                    "module": str(r.get("module", "")),
                    "text": text[:320],
                    "tools": list(dict.fromkeys([str(t) for t in (r.get("tools") or [])]))[:6],
                }
            )
        return compact

    @staticmethod
    def _normalize_session_language(language: Optional[str]) -> str:
        raw = str(language or "tr").strip().lower()
        if raw.startswith("en"):
            return "en"
        if raw.startswith("tr"):
            return "tr"
        return "tr"

    @classmethod
    def _language_directive(cls, language: Optional[str]) -> str:
        lang = cls._normalize_session_language(language)
        if lang == "en":
            return (
                "The user is speaking English. Reply ONLY in English. "
                "Do not use Turkish words or sentences."
            )
        return (
            "Kullanıcı Türkçe konuşuyor. Yalnızca Türkçe yanıt ver. "
            "İngilizce kelime veya cümle kullanma."
        )

    def _adaptive_persona_num_predict(self, user_prompt: str, report_count: int) -> int:
        """Small adaptive budget to reduce latency without clipping useful answers."""
        base = int(self.persona_num_predict)
        prompt = str(user_prompt or "").strip()
        short_prompt = len(prompt) <= 40
        is_direct_question = "?" in prompt or len(prompt.split()) <= 6
        if short_prompt and is_direct_question and report_count <= 1:
            return max(72, min(base, 120))
        if report_count >= 3:
            return min(256, max(base, 160))
        return base

    def step(
        self,
        user_prompt: str = "",
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        language: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        One complete Agent thought cycle with staged execution.

        Stage 1: Immediate ack (100-500ms, template based)
        Stage 2: Plan summary
        Stage 3: Tool execution with progress
        Stage 4: Final persona response
        """
        now = time.time()
        if now - self.last_run < self.cooldown:
            return None
        self.last_run = now

        if self.is_busy or not user_prompt:
            return None

        self.is_busy = True
        previous_hook = self.tool_registry.status_hook

        session_language = self._normalize_session_language(language)

        # ── Create progress token for this request lifecycle ──
        progress_token = self.progress_manager.new_request(language=session_language)
        self._active_progress_token = progress_token

        # Build a unified progress callback that routes through ProgressManager
        def _unified_progress_cb(event: Dict[str, Any]) -> None:
            event["token"] = progress_token
            self.progress_manager.on_progress_event(event)
            # Also call the original callback if provided
            if progress_cb:
                try:
                    progress_cb(event)
                except Exception:
                    pass

        self.tool_registry.status_hook = _unified_progress_cb

        try:
            # ── Stage 1: Immediate acknowledgement ──
            self.progress_manager.emit_ack(progress_token)

            # 1. Collect world & survival context
            survival_override = self.check_survival_drives()
            world_context = self.world_state.inject_world_state("")

            lang_rule = self._language_directive(session_language)
            full_prompt = f"{user_prompt}\n\n[{lang_rule}]\n\n[World State]\n{world_context}"
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

                # ── Stage 2: Plan summary ──
                plan_summary = self._build_plan_summary(user_prompt, self.last_routed_subagents)
                self.progress_manager.emit_plan(progress_token, plan_summary)
                self._emit_progress(_unified_progress_cb, {"type": "plan", "plan": plan_summary})

                # ── Stage 3: Sub-agent execution with progress ──
                if self.last_routed_subagents:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(self.last_routed_subagents), self.subagent_workers)) as ex:
                        futures = {}
                        for module_name in self.last_routed_subagents:
                            profile = self.subagent_profiles.get(module_name)
                            if not profile:
                                continue
                            fut = ex.submit(
                                self._run_subagent,
                                profile,
                                user_prompt,
                                world_context,
                                survival_override,
                                active_model,
                                _unified_progress_cb,
                            )
                            futures[fut] = module_name

                        for fut in concurrent.futures.as_completed(futures):
                            try:
                                report = fut.result()
                            except Exception as exc:
                                self._safe_log_warning("Sub-agent %s failed in executor: %s", futures.get(fut), exc)
                                continue
                            subagent_reports.append(report)
                            total_steps += int(report.get("steps", 0))

                if subagent_reports:
                    try:
                        from modules.ollama.services.clients import GoogleAIStudioClient  # type: ignore

                        gemini_limited = GoogleAIStudioClient.is_rate_limited(
                            str(getattr(self.provider_client, "api_key", ""))
                        )
                    except Exception:
                        gemini_limited = False

                    if gemini_limited:
                        if session_language == "en":
                            final_text = (
                                "AI quota is exhausted right now. Can you try again in a minute or two?"
                            )
                        else:
                            final_text = (
                                "Şu an yapay zeka kotası dolu. Bir iki dakika sonra tekrar dener misin?"
                            )
                        self._append_history("assistant", final_text)
                    else:
                        self._emit_progress(_unified_progress_cb, {"type": "persona_start"})
                        final_text = self._synthesize_main_persona(
                            user_prompt=user_prompt,
                            reports=subagent_reports,
                            survival_override=survival_override,
                            active_model=active_model,
                            session_language=session_language,
                        )
                        self._append_history("assistant", final_text)
                else:
                    messages = list(self.chat_history)
                    final_text, total_steps = self._run_native_history_loop(active_model, messages)
            else:
                messages = list(self.chat_history)
                final_text, total_steps = self._run_native_history_loop(active_model, messages)

            # ── Stage 4: Final — cancel stale progress, deliver response ──
            self.progress_manager.emit_final(progress_token)

            # 4. Save to episodic long-term memory + consolidate durable facts
            self.memory.remember("dialogue", f"User: {user_prompt} | Bot: {final_text}")
            try:
                self.memory_consolidator.consolidate(user_prompt, speaker=self._current_speaker())
            except Exception:
                logger.debug("memory consolidation failed", exc_info=True)

            # 5. Return dict matching AutonomyBrain expectations (but empty plan/actions)
            return {
                "text": final_text,
                "thoughts": f"Tri-layer executed with {total_steps} internal steps.",
                "actions": [],
                "plan": plan_summary if 'plan_summary' in locals() else [],
                "route": self.last_routed_subagents,
                "subagents": subagent_reports,
            }

        finally:
            self.progress_manager.emit_final(progress_token)
            self.tool_registry.status_hook = previous_hook
            self._active_progress_token = ""
            self.is_busy = False
