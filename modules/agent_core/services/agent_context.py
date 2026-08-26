from __future__ import annotations

import os as _sentrybot_agent_context_os

def _sentrybot_agent_context_env_ollama_url() -> str:
    return (
        _sentrybot_agent_context_os.environ.get("SENTRYBOT_OLLAMA_BASE_URL")
        or _sentrybot_agent_context_os.environ.get("SENTRYBOT_REMOTE_OLLAMA_URL")
        or _sentrybot_agent_context_os.environ.get("SENTRYBOT_OLLAMA_URL")
        or _sentrybot_agent_context_os.environ.get("OLLAMA_HOST")
        or _sentrybot_agent_context_os.environ.get("OLLAMA_BASE_URL")
        or "http://whoismrsentry.local:11434"
    ).strip().rstrip("/")

def _sentrybot_normalize_ollama_base_url(raw) -> str:
    value = str(raw or "").strip().rstrip("/")
    env_value = _sentrybot_agent_context_env_ollama_url()

    lowered = value.lower()

    if (
        not value
        or lowered in {"http:", "https:", "http", "https"}
        or lowered.startswith("http://http:")
        or lowered.startswith("https://http:")
        or lowered.startswith("http://https:")
        or lowered == "http://http:11434"
        or lowered == "https://http:11434"
        or lowered.endswith("/ollama")
        or lowered.endswith("/ollama/chat")
    ):
        value = env_value

    if value.lower() in {"http:", "https:", "http", "https"}:
        value = "http://whoismrsentry.local:11434"

    if "://" not in value:
        value = "http://" + value

    return value.rstrip("/")



import logging
import os
from typing import Any, Callable, Dict, List, Optional

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
from .tri_layer import TriLayerRouter, build_subagent_profiles
from .vision_arbiter import VisionArbiter
from .world_state import WorldState

logger = logging.getLogger("agent.orchestrator")

try:
    import ollama
except ImportError:
    ollama = None

try:
    from modules.ai_provider.services.clients import create_llm_client
except Exception:
    create_llm_client = None


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
        if ollama:
            try:
                self.ollama_base_url = _sentrybot_normalize_ollama_base_url(getattr(self, "ollama_base_url", None))
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
            client=self.autonomy_client, memory=self.memory, slam=self.slam,
            world_state=self.world_state, safety_filter=self.safety_filter,
            tool_execution_arbiter=self.tool_execution_arbiter, vision_arbiter=self.vision_arbiter,
            vlm_ask_timeout_s=float((config.get("tool_execution", {}) or {}).get("timeout_s", 22.0)),
            gateway_base_url=self._gateway_base_url,
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
        profile_overrides = tri_cfg.get("profiles") if isinstance(tri_cfg.get("profiles"), dict) else None
        self.subagent_profiles = build_subagent_profiles(profile_overrides)
        self.router = TriLayerRouter(
            profiles=self.subagent_profiles,
            max_subagents=self._safe_int(router_cfg.get("max_subagents", 2), fallback=2, minimum=1),
            default_modules=default_modules,
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
        self.persona_stream_enabled = bool(persona_cfg.get("stream_enabled", False))
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
        messages = [{"role": "system", "content": base_system}]
        messages.extend(self.chat_history)
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def check_survival_drives(self) -> Optional[str]:
        if not self.autonomy_client or not hasattr(self.autonomy_client, "get_hardware_status"):
            return None
        try:
            status = self.autonomy_client.get_hardware_status()
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

    def _check_provider_availability(self) -> None:
        if self.llm_provider != "ollama" and self.provider_client is None:
            raise RuntimeError(f"Provider {self.llm_provider} is not available")
