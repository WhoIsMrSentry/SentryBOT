from __future__ import annotations

from contextlib import nullcontext
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from modules.common.ollama_url import normalize_ollama_url

from .action_arbiter import ActionArbiter
from .agent_handlers import register_default_action_handlers
from .agent_memory_sync import AgentMemorySyncMixin
from .expression_arbiter import ExpressionArbiter
from .idle_behavior import IdleBehaviorSystem
from .memory import EpisodicMemory
from .progress import ProgressManager
from .safety_filter import ActionSafetyFilter
from .sensor_loop import SensorFeedbackLoop
from .slam import TopologicalMap
from .speech_arbiter import SpeechArbiter
from .tool_execution_arbiter import ToolExecutionArbiter
from .tools import ToolRegistry
from .tri_layer import TriLayerRouter
from .vision_arbiter import VisionArbiter
from .world_state import WorldState

logger = logging.getLogger("agent.orchestrator")

try:
    import ollama
except ImportError:
    ollama = None

try:
    from modules.ai_provider.services.clients import _INFERENCE_SCHEDULER, create_llm_client
except Exception:
    create_llm_client = None
    _INFERENCE_SCHEDULER = None


class _PriorityOllamaAdapter:
    """Wrap stock ollama.Client with PriorityInferenceLock while filtering ``priority``."""

    supports_priority = True

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def chat(self, *, priority: int = 0, **kwargs: Any) -> Any:
        guard = (
            _INFERENCE_SCHEDULER.acquire(priority=int(priority))
            if _INFERENCE_SCHEDULER is not None
            else nullcontext()
        )
        with guard:
            return self._inner.chat(**kwargs)

    def list(self) -> Any:
        return self._inner.list()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


class AgentContextMixin(AgentMemorySyncMixin):
    """Initialization and context management methods for AgentOrchestrator."""

    config: Dict[str, Any]
    autonomy_client: Any
    world_state: WorldState
    memory: EpisodicMemory
    memory_consolidator: Any
    slam: TopologicalMap
    safety_filter: ActionSafetyFilter
    tool_execution_arbiter: ToolExecutionArbiter
    action_arbiter: ActionArbiter
    vision_arbiter: VisionArbiter
    expression_arbiter: ExpressionArbiter
    speech_arbiter: SpeechArbiter
    progress_manager: ProgressManager
    tool_registry: ToolRegistry
    sensor_loop: SensorFeedbackLoop
    idle_system: IdleBehaviorSystem
    router: TriLayerRouter
    subagent_profiles: Dict[str, Any]
    chat_history: List[Dict[str, Any]]
    max_history: int
    model: str
    temperature: float
    num_ctx: int
    cooldown: float
    llm_provider: str
    clm_fallback_enabled: bool
    clm_fallback_model: str
    fallback_on_missing_model: bool
    fallback_on_error: bool
    ollama_think: Any
    ollama_keep_alive: Any
    request_timeout: float
    status_interval_s: float
    max_steps: int
    ollama_base_url: str
    ollama_client: Any
    provider_client: Any
    provider_name: str
    _cached_model_names: List[str]
    _cached_model_names_ts: float
    _gateway_base_url: str
    _action_http_timeout_s: float
    tri_layer_enabled: bool
    api_native_tools: bool
    fast_path_enabled: bool
    fast_path_max_chars: int
    fast_path_num_predict: int
    fast_path_max_steps: int
    subagent_max_steps: int
    subagent_workers: int
    persona_system_prompt: str
    persona_num_predict: int
    persona_stream_enabled: bool
    chat_num_predict: int

    def _init_gateway_config(self, config: Dict[str, Any]) -> None:
        actions_cfg = config.get("actions", {}) if isinstance(config.get("actions", {}), dict) else {}
        try:
            from modules.gateway.url import resolve_config_url, resolve_gateway_base_url
            default_gw = resolve_gateway_base_url(self.config)
            raw_gw = str(actions_cfg.get("gateway_base_url", default_gw)).strip()
            self._gateway_base_url = resolve_config_url(raw_gw, default_gw).rstrip("/")
        except Exception:
            self._gateway_base_url = str(actions_cfg.get("gateway_base_url", "http://127.0.0.1:8080")).rstrip("/")
        self._action_http_timeout_s = float(actions_cfg.get("http_timeout_s", 2.5))

    def _init_llm_settings(self, config: Dict[str, Any]) -> Dict[str, Any]:
        agent_cfg = config.get("agent", {})
        self.model = agent_cfg.get("model", "llama3.2:3b-q4_K_M")
        self.temperature = agent_cfg.get("temperature", 0.15)
        self.num_ctx = agent_cfg.get("num_ctx", 4096)
        self.cooldown = agent_cfg.get("cooldown_s", 1.0)
        llm_cfg = config.get("llm", {}) if isinstance(config.get("llm", {}), dict) else {}
        self.llm_provider = str(llm_cfg.get("provider", "ollama")).strip().lower() or "ollama"
        self.clm_fallback_enabled = bool(llm_cfg.get("clm_fallback_enabled", True))
        self.clm_fallback_model = str(llm_cfg.get("clm_fallback_model", agent_cfg.get("clm_fallback_model", ""))).strip()
        self.fallback_on_missing_model = bool(llm_cfg.get("fallback_on_missing_model", True))
        self.fallback_on_error = bool(llm_cfg.get("fallback_on_error", True))
        self.ollama_think = llm_cfg.get("think", False)
        self.ollama_keep_alive = llm_cfg.get("keep_alive", -1)
        self.request_timeout = self._safe_float(
            agent_cfg.get("request_timeout", agent_cfg.get("ollama_request_timeout", 60.0)), fallback=60.0, minimum=1.0,
        )
        self.status_interval_s = self._safe_float(agent_cfg.get("status_interval_s", 2.0), fallback=2.0, minimum=0.2)
        self.max_steps = self._safe_int(
            agent_cfg.get("max_steps", agent_cfg.get("max_tool_loops", 10)), fallback=10, minimum=1,
        )
        self.ollama_base_url = self._resolve_ollama_base_url(agent_cfg)
        if self.llm_provider != "ollama":
            logger.info("Agent Core running in provider mode: %s (limited tool-calling adaptation enabled)", self.llm_provider)
        return agent_cfg

    def _init_llm_clients(self) -> None:
        self.ollama_client = None
        self.provider_client = None
        self.provider_name = self.llm_provider
        self._cached_model_names = []
        self._cached_model_names_ts = 0.0
        self._ollama_unavailable_until = 0.0
        self._ollama_unavailable_reason = ""
        self._ollama_probe_ok_until = 0.0
        if ollama:
            try:
                self.ollama_base_url = normalize_ollama_url(getattr(self, "ollama_base_url", None))
                raw_client = ollama.Client(host=self.ollama_base_url, timeout=self.request_timeout)
                self.ollama_client = _PriorityOllamaAdapter(raw_client)
            except Exception as exc:
                logger.warning("Ollama client init failed for host %s: %s", self.ollama_base_url, exc)
                try:
                    raw_client = ollama.Client(host=self.ollama_base_url)
                    self.ollama_client = _PriorityOllamaAdapter(raw_client)
                except Exception:
                    self.ollama_client = None
        if self.llm_provider != "ollama" and create_llm_client:
            try:
                self.provider_client, self.provider_name = create_llm_client(self.config)
                logger.info("LLM provider client ready: %s (model=%s)", self.provider_name, getattr(self.provider_client, "model", ""))
            except Exception as exc:
                logger.error("Provider client init failed for %s: %s", self.llm_provider, exc)

    def _init_subsystems(self, config: Dict[str, Any]) -> None:
        self.world_state = WorldState()
        self.memory = EpisodicMemory()
        self.memory_consolidator = self._build_memory_consolidator()
        self.slam = TopologicalMap()
        self.safety_filter = ActionSafetyFilter(config)
        if hasattr(self.safety_filter, "set_world_state"):
            self.safety_filter.set_world_state(self.world_state)
        self.tool_execution_arbiter = ToolExecutionArbiter()
        self.action_arbiter = ActionArbiter(safety_filter=self.safety_filter)
        self.vision_arbiter = VisionArbiter()
        expression_lease_cfg = config.get("expression_lease", {}) if isinstance(config.get("expression_lease"), dict) else {}
        from modules.common.led_write_policy import get_shared_policy

        self.expression_arbiter = get_shared_policy(expression_lease_cfg)
        self.speech_arbiter = SpeechArbiter()
        progress_cfg = config.get("progress", {}) if isinstance(config.get("progress", {}), dict) else {}
        self.progress_manager = ProgressManager(
            speech_arbiter=self.speech_arbiter,
            persona_start_min_elapsed_s=self._safe_float(
                progress_cfg.get("persona_start_min_elapsed_s", 4.0), fallback=4.0, minimum=0.0,
            ),
            interaction_emit_fn=(
                self.autonomy_client.push_interaction_event
                if self.autonomy_client and hasattr(self.autonomy_client, "push_interaction_event")
                else None
            ),
        )
        self.progress_manager.attach_arbiters(
            action_arbiter=self.action_arbiter, vision_arbiter=self.vision_arbiter,
            expression_arbiter=self.expression_arbiter, tool_execution_arbiter=self.tool_execution_arbiter,
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
            action_arbiter=self.action_arbiter,
            expression_arbiter=self.expression_arbiter,
            mcp_client=getattr(self, "mcp_client", None),
        )
        runtime_cfg = config.get("agent_runtime", {}) if isinstance(config.get("agent_runtime"), dict) else {}
        from .runtime import CapabilityIndex, DecisionTraceStore, FailureClassifier, GoalStore, ProgressTracker, RecoveryManager
        from .runtime.native_tool_recovery import NativeToolRecovery

        self.decision_traces = DecisionTraceStore(
            maxlen=int(runtime_cfg.get("decision_trace_maxlen", 64)),
            log_path=runtime_cfg.get("decision_trace_log_path") or None,
            max_bytes=int(runtime_cfg.get("decision_trace_log_max_bytes", 262144)),
            backup_count=int(runtime_cfg.get("decision_trace_log_backups", 2)),
        )
        gp_cfg = runtime_cfg.get("goal_persistence") if isinstance(runtime_cfg.get("goal_persistence"), dict) else {}
        self.goal_store = GoalStore(
            enabled=bool(gp_cfg.get("enabled", True)),
            backend=str(gp_cfg.get("backend", "memory")),
            ttl_s=float(gp_cfg.get("ttl_s", 600.0)),
            db_path=gp_cfg.get("db_path") or None,
        )
        self.capability_index = CapabilityIndex.from_robot_registry()
        self.failure_classifier = FailureClassifier()
        self.recovery_manager = RecoveryManager()
        self.native_progress = ProgressTracker(
            max_identical=int(runtime_cfg.get("max_identical_actions", 3)),
            max_zero_progress=int(runtime_cfg.get("max_zero_progress", 3)),
        )
        self._native_tool_recovery_factory = lambda goal_id="native_turn": NativeToolRecovery(
            classifier=self.failure_classifier,
            recovery=self.recovery_manager,
            capabilities=self.capability_index,
            progress=ProgressTracker(
                max_identical=int(runtime_cfg.get("max_identical_actions", 3)),
                max_zero_progress=int(runtime_cfg.get("max_zero_progress", 3)),
            ),
            traces=self.decision_traces,
            max_retries=int(
                (config.get("tool_execution", {}) or {}).get(
                    "max_retries", runtime_cfg.get("max_retries", 1)
                )
            ),
            goal_id=goal_id,
        )

    def _init_background_threads(self) -> None:
        sensor_cfg = self.config.get("sensor_loop", {}) if isinstance(self.config.get("sensor_loop", {}), dict) else {}
        self.sensor_loop = SensorFeedbackLoop(
            self.world_state,
            client=self.autonomy_client,
            enabled=bool(sensor_cfg.get("enabled", True)),
            poll_hz=self._safe_float(sensor_cfg.get("poll_hz", 2.0), fallback=2.0, minimum=0.1),
            hardware_interval_s=self._safe_float(sensor_cfg.get("hardware_interval_s", 2.0), fallback=2.0, minimum=0.2),
            vision_results_interval_s=self._safe_float(sensor_cfg.get("vision_results_interval_s", 5.0), fallback=5.0, minimum=0.5),
            visual_context_interval_s=self._safe_float(sensor_cfg.get("visual_context_interval_s", 10.0), fallback=10.0, minimum=1.0),
            skip_hardware_on_pc=bool(sensor_cfg.get("skip_hardware_on_pc", True)),
        )
        self.idle_system = IdleBehaviorSystem(self, client=self.autonomy_client)
        if self.autonomy_client and hasattr(self.autonomy_client, "set_stt_suppressed"):
            self.speech_arbiter.set_tts_state_callback(lambda active: self.autonomy_client.set_stt_suppressed(bool(active)))
        if self.autonomy_client and hasattr(self.autonomy_client, "stop_speaking"):
            self.speech_arbiter.set_stop_playback_fn(self.autonomy_client.stop_speaking)
        if self.autonomy_client and hasattr(self.autonomy_client, "speak_preferred"):
            self.speech_arbiter.set_speak_fn(
                lambda text, tone=None, language=None, trace_id=None: self.autonomy_client.speak_preferred(
                    text,
                    tone=tone,
                    language=language or "tr",
                    trace_id=trace_id,
                )
            )
        else:
            self.speech_arbiter.set_speak_fn(
                lambda text, tone=None, language=None, trace_id=None: self._handle_speak_fallback(
                    text,
                    tone=tone,
                    language=language or "tr",
                    trace_id=trace_id,
                )
            )
        self._register_action_handlers()

    def _init_chat_history(self, agent_cfg: Dict[str, Any]) -> None:
        self.chat_history = []
        self.max_history = agent_cfg.get("max_history", 10)
        self._history_lock = threading.RLock()

    def _init_tri_layer(self, config: Dict[str, Any], agent_cfg: Dict[str, Any]) -> None:
        tri_cfg = config.get("tri_layer", {}) if isinstance(config.get("tri_layer", {}), dict) else {}
        router_cfg = tri_cfg.get("router", {}) if isinstance(tri_cfg.get("router", {}), dict) else {}
        subagent_cfg = tri_cfg.get("subagent", {}) if isinstance(tri_cfg.get("subagent", {}), dict) else {}
        persona_cfg = tri_cfg.get("persona", {}) if isinstance(tri_cfg.get("persona", {}), dict) else {}
        default_modules = router_cfg.get("default_modules", ["autonomy", "agent_core"])
        if not isinstance(default_modules, list):
            default_modules = ["autonomy", "agent_core"]
        if not self._vision_input_available():
            default_modules = [m for m in default_modules if str(m).strip().lower() != "vlm_bridge"]
        profiles_override = tri_cfg.get("profiles") if isinstance(tri_cfg.get("profiles"), dict) else None
        from .tri_layer import build_subagent_profiles
        self.subagent_profiles = build_subagent_profiles(profiles_override)
        from .laya_engine import LayaEngine

        self.laya_engine = LayaEngine.get_instance(config)
        self.sensor_loop.laya_engine = self.laya_engine
        self.router = TriLayerRouter(
            profiles=self.subagent_profiles,
            max_subagents=self._safe_int(router_cfg.get("max_subagents", 2), fallback=2, minimum=1),
            default_modules=default_modules,
            laya_engine=self.laya_engine,
        )
        self.tri_layer_enabled = bool(tri_cfg.get("enabled", True))
        self.api_native_tools = bool(tri_cfg.get("api_native_tools", False))
        fast_cfg = tri_cfg.get("fast_path", {}) if isinstance(tri_cfg.get("fast_path"), dict) else {}
        self.fast_path_enabled = bool(fast_cfg.get("enabled", True))
        self.fast_path_max_chars = self._safe_int(fast_cfg.get("max_chars", 32), fallback=32, minimum=1)
        self.fast_path_num_predict = self._safe_int(fast_cfg.get("num_predict", 80), fallback=80, minimum=10)
        self.fast_path_max_steps = self._safe_int(fast_cfg.get("max_steps", 2), fallback=2, minimum=1)
        self.subagent_max_steps = self._safe_int(subagent_cfg.get("max_steps", 4), fallback=4, minimum=1)
        self.subagent_workers = self._safe_int(subagent_cfg.get("max_parallel_workers", 3), fallback=3, minimum=1)
        self.persona_system_prompt = str(
            persona_cfg.get(
                "system_prompt",
                "You are SentryBOT Companion persona. Speak directly to the user in a friendly, concise tone.",
            )
        )
        self.persona_num_predict = self._safe_int(persona_cfg.get("num_predict", 160), fallback=160, minimum=10)
        self.persona_stream_enabled = bool(persona_cfg.get("stream_enabled", persona_cfg.get("stream", False)))
        self.chat_num_predict = self._safe_int(agent_cfg.get("chat_num_predict", 120), fallback=120, minimum=10)

    def _vision_input_available(self) -> bool:
        if self.autonomy_client and hasattr(self.autonomy_client, "is_vision_input_available"):
            try:
                return bool(self.autonomy_client.is_vision_input_available())
            except Exception:
                return False
        return True

    def _register_action_handlers(self) -> None:
        register_default_action_handlers(self)

    def _resolve_ollama_base_url(self, agent_cfg: Dict[str, Any]) -> str:
        try:
            from modules.ai_provider.services.clients import resolve_ollama_base_url
            return resolve_ollama_base_url(self.config, agent_cfg.get("ollama_base_url", "http:"))
        except Exception:
            return str(agent_cfg.get("ollama_base_url", "http:"))

    @staticmethod
    def _safe_float(value: Any, fallback: float = 0.0, minimum: Optional[float] = None) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = float(fallback)
        if minimum is not None:
            parsed = max(float(minimum), parsed)
        return parsed

    @staticmethod
    def _safe_int(value: Any, fallback: int = 0, minimum: Optional[int] = None) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = int(fallback)
        if minimum is not None:
            parsed = max(int(minimum), parsed)
        return parsed

    def build_context(self, user_prompt: str, system_override: Optional[str] = None) -> List[Dict[str, Any]]:
        survival_override = self.check_survival_drives()
        base_system = system_override or "You are SentryBOT, a companion robot. Help the user."
        if survival_override:
            base_system = f"{base_system}\n\n{survival_override}"
        rag_note = self._chat_rag_note(user_prompt)
        if rag_note:
            base_system = f"{base_system}\n\n{rag_note}"
        messages = [{"role": "system", "content": base_system}]
        get_snap = getattr(self, "_get_history_snapshot", None)
        messages.extend(get_snap() if callable(get_snap) else list(self.chat_history))
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _chat_rag_note(self, user_prompt: str) -> str:
        try:
            from modules.cognitive_memory.services.chat_rag import get_default

            rag = get_default()
            if not rag.enabled:
                return ""
            limit = int(rag.cfg.get("recall_limit", 6) or 6)
            built = rag.build_context(user_prompt, limit=limit)
            items = built.get("items") or []
            if not items:
                return ""
            lines = [f"- [{item.get('role', 'chat')}] {item.get('text', '')}" for item in items[:limit]]
            joined = "\n".join(line for line in lines if line.strip())
            if not joined:
                return ""
            return (
                "[LONG-TERM CHAT MEMORY] Earlier related exchanges you may recall "
                "(never claim certainty; use only if relevant):\n" + joined
            )
        except Exception:
            return ""

    def check_survival_drives(self) -> Optional[str]:
        """Overrides logic if critical battery or temperature limits are reached."""
        world_state = getattr(self, "world_state", None)
        if world_state is not None and hasattr(world_state, "get_state"):
            try:
                state = world_state.get_state() or {}
                if isinstance(state, dict):
                    bat = state.get("battery_percent", 100)
                    if bat is not None and float(bat) < 15.0:
                        logger.warning("SURVIVAL DRIVE: Low Battery (%s%%)!", bat)
                        return "[CRITICAL] Battery is severely low. Do not engage in lengthy tasks. Find a charger or warn the user."
                    ws_temp = state.get("cpu_temp")
                    if ws_temp is not None and float(ws_temp) > 80.0:
                        logger.warning("SURVIVAL DRIVE: High CPU Temp (%s°C)!", ws_temp)
                        return f"[SURVIVAL OVERRIDE] Core temperature high ({ws_temp}°C). Reduce heavy computation."
            except Exception:
                pass

        autonomy_client = getattr(self, "autonomy_client", None)
        if not autonomy_client or not hasattr(autonomy_client, "get_hardware_status"):
            return None
        try:
            status = autonomy_client.get_hardware_status()
            if not isinstance(status, dict):
                return None
            battery = status.get("battery_level")
            temp = status.get("cpu_temp")
            if battery is not None and float(battery) < 15.0:
                return f"[SURVIVAL OVERRIDE] Battery is critically low ({battery}%). Recommend charging immediately."
            if temp is not None and float(temp) > 80.0:
                return f"[SURVIVAL OVERRIDE] Core temperature high ({temp}°C). Reduce heavy computation."
        except Exception:
            pass
        return None

    @staticmethod
    def _is_real_ollama_client(client: Any) -> bool:
        if client is None or ollama is None:
            return False
        ollama_cls = getattr(ollama, "Client", None)
        if not isinstance(ollama_cls, type):
            return False
        inner = getattr(client, "_inner", client)
        return isinstance(inner, ollama_cls)

    @staticmethod
    def _is_provider_transport_error(exc: BaseException) -> bool:
        if isinstance(exc, (ConnectionError, TimeoutError, OSError, requests.exceptions.RequestException)):
            return True
        if type(exc).__name__ in {
            "CircuitOpenError",
            "ConnectError",
            "ConnectTimeout",
            "ReadTimeout",
            "WriteTimeout",
            "PoolTimeout",
            "NetworkError",
            "RemoteProtocolError",
        }:
            return True
        try:
            import httpx

            if isinstance(exc, httpx.TransportError):
                return True
        except Exception:
            pass
        try:
            import httpcore

            if isinstance(exc, (httpcore.NetworkError, httpcore.TimeoutException)):
                return True
        except Exception:
            pass
        return False

    def _mark_ollama_unavailable(self, reason: Any, ttl_s: float = 5.0) -> None:
        self._ollama_probe_ok_until = 0.0
        self._ollama_unavailable_until = time.monotonic() + max(0.5, float(ttl_s))
        self._ollama_unavailable_reason = str(reason or "ollama_unavailable")

    def _probe_ollama_connectivity(self) -> Optional[str]:
        now = time.monotonic()
        unavail_until = float(getattr(self, "_ollama_unavailable_until", 0.0) or 0.0)
        if unavail_until > now:
            return str(getattr(self, "_ollama_unavailable_reason", "") or "ollama_unavailable")

        client = getattr(self, "ollama_client", None)
        if client is None:
            return "ollama_client_missing"
        if not self._is_real_ollama_client(client):
            return None

        ok_until = float(getattr(self, "_ollama_probe_ok_until", 0.0) or 0.0)
        if ok_until > now:
            return None

        base_url = str(getattr(self, "ollama_base_url", "") or "").strip().rstrip("/")
        if not base_url:
            return "ollama_base_url_missing"

        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=0.6)
            status = int(getattr(resp, "status_code", 0) or 0)
            if status >= 500 or status == 0:
                reason = f"http_{status}"
                self._mark_ollama_unavailable(reason)
                return reason
            self._ollama_probe_ok_until = time.monotonic() + 5.0
            self._ollama_unavailable_until = 0.0
            self._ollama_unavailable_reason = ""
            return None
        except Exception as exc:
            self._mark_ollama_unavailable(exc)
            return str(exc)

    def _provider_unavailable_payload(
        self,
        *,
        session_language: str = "tr",
        event_type: Optional[str] = None,
        reason: str = "",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        lang = str(session_language or "tr").strip().lower()
        if event_type:
            text = ""
        elif lang.startswith("en"):
            text = "LLM provider is currently unreachable."
        else:
            text = "LLM servisine su anda ulasilamiyor."
        payload: Dict[str, Any] = {
            "ok": False,
            "error": "ollama_unavailable",
            "text": text,
            "thoughts": f"LLM unavailable: {reason}" if reason else "LLM unavailable.",
            "actions": [],
            "plan": [],
        }
        if reason:
            payload["detail"] = reason
        if trace_id is not None:
            payload["trace_id"] = trace_id
        return payload

    def _check_provider_availability(self) -> Optional[Dict[str, Any]]:
        if self.llm_provider != "ollama":
            if self.provider_client is None:
                return {
                    "ok": False,
                    "error": "provider_unavailable",
                    "text": f"Provider {self.llm_provider} is not available",
                    "thoughts": f"Provider {self.llm_provider} is not available.",
                    "actions": [],
                    "plan": [],
                }
            return None
        reason = self._probe_ollama_connectivity()
        if reason:
            return self._provider_unavailable_payload(reason=reason)
        return None

    def create_agent_runtime(self, **budget_overrides: Any):
        """Build a typed AgentRuntime bound to this orchestrator's ToolRegistry.

        Additive helper — does not change the speech turn path. Callers that need
        multi-step goal solving with recovery/traces should use this instead of
        inventing a parallel loop.
        """
        from .runtime import AgentRuntime, Budget, CapabilityIndex, ProgressTracker

        cfg = self.config.get("agent_runtime", {}) if isinstance(self.config.get("agent_runtime"), dict) else {}
        if not bool(cfg.get("enabled", True)):
            raise RuntimeError("agent_runtime disabled in config")

        budget = Budget(
            max_iterations=int(budget_overrides.get("max_iterations", cfg.get("max_iterations", 6))),
            max_tool_calls=int(budget_overrides.get("max_tool_calls", cfg.get("max_tool_calls", 8))),
            max_retries=int(budget_overrides.get("max_retries", cfg.get("max_retries", 2))),
            max_replans=int(budget_overrides.get("max_replans", cfg.get("max_replans", 2))),
            max_execution_time_s=float(
                budget_overrides.get("max_execution_time_s", cfg.get("max_execution_time_s", 60.0))
            ),
        )
        runtime = AgentRuntime(
            tool_executor=self.tool_registry.execute,
            capability_index=getattr(self, "capability_index", None) or CapabilityIndex.from_robot_registry(),
            budget=budget,
            available_tools=self.tool_registry.get_tool_names(),
        )
        runtime.progress = ProgressTracker(
            max_identical=int(cfg.get("max_identical_actions", 3)),
            max_zero_progress=int(cfg.get("max_zero_progress", 3)),
        )
        if getattr(self, "decision_traces", None) is not None:
            runtime.traces = self.decision_traces
        return runtime
