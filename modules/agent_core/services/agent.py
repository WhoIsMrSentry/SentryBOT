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
from modules.common.latency_trace import latency_trace

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
        self.config = config
        self.autonomy_client = autonomy_client
        self._warn_insecure_defaults(config)

        self._init_gateway_config(config)
        agent_cfg = self._init_llm_settings(config)
        self._init_llm_clients()
        self._init_subsystems(config)
        self._init_background_threads()
        self._init_chat_history(agent_cfg)
        self._init_tri_layer(config, agent_cfg)

        self.last_run = 0.0
        self.is_busy = False
        self._active_progress_token: str = ""
        self.last_routed_subagents: List[str] = []

    def _init_gateway_config(self, config):
        actions_cfg = config.get("actions", {}) if isinstance(config.get("actions", {}), dict) else {}
        try:
            from modules.gateway.url import resolve_config_url, resolve_gateway_base_url
            default_gw = resolve_gateway_base_url(self.config)
            raw_gw = str(actions_cfg.get("gateway_base_url", default_gw)).strip()
            self._gateway_base_url = resolve_config_url(raw_gw, default_gw).rstrip("/")
        except Exception:
            self._gateway_base_url = str(actions_cfg.get("gateway_base_url", "http://127.0.0.1:8080")).rstrip("/")
        self._action_http_timeout_s = float(actions_cfg.get("http_timeout_s", 2.5))

    def _init_llm_settings(self, config) -> dict:
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

    def _init_llm_clients(self):
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
                logger.info("LLM provider client ready: %s (model=%s)", self.provider_name, getattr(self.provider_client, "model", ""))
            except Exception as exc:
                logger.error("Provider client init failed for %s: %s", self.llm_provider, exc)

    def _init_subsystems(self, config):
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
        self.expression_arbiter = ExpressionArbiter(expression_lease_cfg)
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

    def _init_background_threads(self):
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

    def _init_chat_history(self, agent_cfg):
        self.chat_history = []
        self.max_history = agent_cfg.get("max_history", 10)

    def _init_tri_layer(self, config, agent_cfg):
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
        fast_cfg = tri_cfg.get("fast_path", {}) if isinstance(tri_cfg.get("fast_path", {}), dict) else {}
        self.fast_path_enabled = bool(fast_cfg.get("enabled", True))
        self.fast_path_max_chars = self._safe_int(fast_cfg.get("max_chars", 140), fallback=140, minimum=20)
        self.fast_path_num_predict = self._safe_int(fast_cfg.get("num_predict", 96), fallback=96, minimum=32)
        self.fast_path_max_steps = self._safe_int(fast_cfg.get("max_steps", 2), fallback=2, minimum=1)
        self.subagent_max_steps = self._safe_int(subagent_cfg.get("max_steps", 2), fallback=2, minimum=1)
        self.subagent_workers = self._safe_int(subagent_cfg.get("workers", 2), fallback=2, minimum=1)
        self.persona_system_prompt = str(persona_cfg.get("system_prompt", "")).strip()
        self.persona_num_predict = self._safe_int(persona_cfg.get("num_predict", 180), fallback=180, minimum=64)
        self.persona_stream_enabled = bool(persona_cfg.get("stream", True))
        self.chat_num_predict = self._safe_int(agent_cfg.get("num_predict", 100), fallback=100, minimum=48)
        rt_cfg = config.get("realtime_profile", {}) if isinstance(config.get("realtime_profile", {}), dict) else {}
        active_profile_name = str(rt_cfg.get("active", "")).strip().lower()
        profiles_map = rt_cfg.get("profiles", {}) if isinstance(rt_cfg.get("profiles", {}), dict) else {}
        active_profile = profiles_map.get(active_profile_name, {}) if active_profile_name else {}
        if not isinstance(active_profile, dict) or not active_profile:
            active_profile = rt_cfg.get(active_profile_name, {}) if active_profile_name else {}
        if isinstance(active_profile, dict) and active_profile:
            self.apply_realtime_profile(active_profile)

    def _build_memory_consolidator(self):
        """Wire the consolidator to episodic memory, autonomy client, and LLM.

        This bridges dialogue -> semantic facts -> WorldMemory (RAG) + episodic + social.
        """
        from .memory_consolidator import MemoryConsolidator

        social_db = None
        try:
            from modules.social_db import get_default as _social_default  # type: ignore

            social_db = _social_default()
        except Exception:
            social_db = None

        # Use provider client for extraction (works with ollama/openai/gemini)
        llm_client = getattr(self, "provider_client", None) or getattr(self, "ollama_client", None)

        return MemoryConsolidator(
            memory=self.memory,
            social_db=social_db,
            autonomy_client=self.autonomy_client,
            llm_client=llm_client,
        )

    def _get_world_memory_context(self, user_prompt: str, limit: int = 8) -> str:
        autonomy_client = getattr(self, "autonomy_client", None)
        if not autonomy_client or not hasattr(autonomy_client, "world_memory_context"):
            return ""
        try:
            result = autonomy_client.world_memory_context(user_prompt, limit=limit)
            if isinstance(result, dict):
                return str(result.get("context") or "").strip()
        except Exception:
            logger.debug("world memory context lookup failed", exc_info=True)
        return ""

    def _observe_world_memory_dialogue(self, user_prompt: str, final_text: str) -> None:
        autonomy_client = getattr(self, "autonomy_client", None)
        if not autonomy_client or not hasattr(autonomy_client, "world_memory_observe"):
            return
        text = str(user_prompt or "").strip()
        reply = str(final_text or "").strip()
        if not text and not reply:
            return
        try:
            autonomy_client.world_memory_observe({
                "kind": "episode",
                "name": "dialogue",
                "summary": ("User: " + text + " | Robot: " + reply)[:800],
                "confidence": 0.62,
                "salience": 0.55,
                "tags": ["dialogue", "conversation"],
                "details": {"user": text, "assistant": reply, "speaker": self._current_speaker()},
            })
        except Exception:
            logger.debug("dialogue world memory write failed", exc_info=True)

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

    def _handle_speak_fallback(self, text: str, tone: Optional[Dict[str, Any]] = None, language: Optional[str] = None, trace_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            import requests  # type: ignore
            url = f"{self._gateway_base_url}/speak/say"
            resp = requests.post(
                url,
                json={"text": text, "tone": tone, "language": language or "tr", "trace_id": trace_id},
                timeout=self._action_http_timeout_s,
            )
            return resp.json() if resp.status_code == 200 else {"ok": False, "status": resp.status_code}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

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

    def _apply_profile_field(self, applied: Dict[str, Any], profile: Dict[str, Any],
                             key: str, attr: str, converter: str = "int",
                             fallback: Any = None, minimum: Any = None) -> None:
        if key not in profile:
            return
        raw = profile[key]
        if converter == "int":
            value = self._safe_int(raw, fallback=fallback if fallback is not None else getattr(self, attr, 0), minimum=minimum)
        else:
            value = self._safe_float(raw, fallback=fallback if fallback is not None else getattr(self, attr, 0.0), minimum=minimum)
        setattr(self, attr, value)
        applied[key] = value

    def apply_realtime_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(profile, dict):
            return {}

        _FIELDS = [
            ("num_predict_persona", "persona_num_predict", "int", 64),
            ("num_predict_chat", "chat_num_predict", "int", 48),
            ("num_ctx", "num_ctx", "int", 512),
            ("temperature", "temperature", "float", 0.0),
            ("request_timeout_s", "request_timeout", "float", 1.0),
            ("subagent_workers", "subagent_workers", "int", 1),
            ("subagent_max_steps", "subagent_max_steps", "int", 1),
        ]
        applied: Dict[str, Any] = {}
        for key, attr, conv, minimum in _FIELDS:
            self._apply_profile_field(applied, profile, key, attr, conv, minimum=minimum)

        if "max_subagents" in profile:
            value = self._safe_int(profile["max_subagents"], fallback=getattr(self.router, "max_subagents", 2), minimum=1)
            if hasattr(self.router, "set_max"):
                applied["max_subagents"] = self.router.set_max(value)
            else:
                self.router.max_subagents = value
                applied["max_subagents"] = self.router.max_subagents

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

    def _warn_insecure_defaults(self, config: dict) -> None:
        """Log warnings for insecure default credentials."""
        warnings = []
        
        # Check agent.yaml auth_token
        agent_cfg = config.get("agent", {}) if isinstance(config.get("agent", {}), dict) else {}
        auth_token = str(agent_cfg.get("auth_token", "") or "").strip()
        if auth_token in ("", "changeme", "your-auth-token", "replace_me"):
            warnings.append("SECURITY WARNING: agent.auth_token is using default/empty value 'changeme' - please set a strong token in config/agent.yaml")
        
        # Check vlm_bridge auth_token
        vlm_cfg = config.get("vlm_bridge", {}) if isinstance(config.get("vlm_bridge", {}), dict) else {}
        remote_cfg = vlm_cfg.get("remote", {}) if isinstance(vlm_cfg.get("remote", {}), dict) else {}
        vlm_auth = str(remote_cfg.get("auth_token", "") or "").strip()
        if vlm_auth in ("", "changeme", "your-auth-token", "replace_me"):
            warnings.append("SECURITY WARNING: vlm_bridge.remote.auth_token is using default/empty value 'changeme' - please set a strong token in config/agent.yaml")
        
        # Check speak remote auth_token. The current config stores it under
        # speak.tts.remote.auth_token; older configs may also use speak.remote.
        speak_cfg = config.get("speak", {}) if isinstance(config.get("speak", {}), dict) else {}
        remote_speak = speak_cfg.get("remote", {}) if isinstance(speak_cfg.get("remote", {}), dict) else {}
        tts_cfg = speak_cfg.get("tts", {}) if isinstance(speak_cfg.get("tts", {}), dict) else {}
        tts_remote = tts_cfg.get("remote", {}) if isinstance(tts_cfg.get("remote", {}), dict) else {}
        speak_auth = str(remote_speak.get("auth_token", "") or tts_remote.get("auth_token", "") or "").strip()
        if speak_auth in ("", "changeme", "your-auth-token", "replace_me"):
            warnings.append("SECURITY WARNING: speak.tts.remote.auth_token is using default/empty value - please set a strong token in config/agent.yaml")
        
        # Check esp_link WiFi password
        esp_cfg = config.get("esp_link", {}) if isinstance(config.get("esp_link", {}), dict) else {}
        network_cfg = esp_cfg.get("network", {}) if isinstance(esp_cfg.get("network", {}), dict) else {}
        wifi_password = str(network_cfg.get("password", "") or "").strip()
        wifi_ssid = str(network_cfg.get("ssid", "") or "").strip()
        if wifi_password and wifi_password == wifi_ssid and wifi_ssid == "SentryBOT":
            warnings.append("SECURITY WARNING: esp_link WiFi password equals SSID ('SentryBOT') - please set a strong unique password in modules/esp_link/config/config.yml")
        
        for warning in warnings:
            logger.warning(warning)

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
            from modules.common.vision_availability import camera_live_available
            from modules.gateway.url import resolve_gateway_base_url

            return camera_live_available(resolve_gateway_base_url(), timeout_s=0.35)
        except Exception:
            return False

    def _vision_input_available(self) -> bool:
        try:
            from modules.common.vision_availability import vision_input_available
            from modules.gateway.url import resolve_gateway_base_url

            return vision_input_available(resolve_gateway_base_url(), timeout_s=0.5)
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
        data = self._loads_first_json_object(cleaned)
        if not isinstance(data, dict):
            return None

        tool_name = str(
            data.get("tool") or data.get("tool_name") or data.get("name") or ""
        ).strip()
        if tool_name not in allowed:
            return None

        arguments = data.get("arguments", data.get("args", data.get("parameters", {})))
        if not isinstance(arguments, dict):
            arguments = {}

        return {
            "function": {
                "name": tool_name,
                "arguments": arguments,
            }
        }

    @staticmethod
    def _loads_first_json_object(text: str) -> Optional[Any]:
        """Parse text as JSON; if that fails, extract the first balanced {...} block.

        Prompt-driven providers (Gemma/Gemini) often wrap the JSON tool call in
        prose or code fences despite instructions, so plain json.loads is not
        enough for a reliable multi-turn tool loop.
        """
        candidate = str(text or "").strip()
        if not candidate:
            return None
        try:
            return json.loads(candidate)
        except Exception:
            pass
        start = candidate.find("{")
        while start != -1:
            depth = 0
            for idx in range(start, len(candidate)):
                ch = candidate[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(candidate[start : idx + 1])
                        except Exception:
                            break
            start = candidate.find("{", start + 1)
        return None

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
            # Keep the multi-turn tool trace readable for prompt-based providers:
            # assistant tool_calls have empty content and would silently vanish,
            # breaking the model's picture of what it already executed.
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

    def _call_ollama_chat(self, kwargs: Dict[str, Any]):
        client = getattr(self, "ollama_client", None)
        call = client.chat if client is not None else ollama.chat
        request = dict(kwargs)
        request["think"] = getattr(self, "ollama_think", False)
        keep_alive = getattr(self, "ollama_keep_alive", None)
        if keep_alive is not None:
            request["keep_alive"] = keep_alive
        try:
            return call(**request)
        except TypeError:
            request.pop("think", None)
            try:
                return call(**request)
            except TypeError:
                request.pop("keep_alive", None)
                return call(**request)

    def _chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        options: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"model": self._pick_runtime_model(model), "messages": messages}
        if tools is not None:
            kwargs["tools"] = tools
        if options is not None:
            kwargs["options"] = options

        selected_model = str(kwargs["model"])
        started = time.monotonic()
        if trace_id:
            latency_trace.mark(trace_id, "llm.request", {"model": selected_model, "stream": False})
        try:
            if self.llm_provider != "ollama":
                if self.provider_client is None:
                    raise RuntimeError(f"Provider '{self.llm_provider}' selected but client is not initialized")
                response = self._chat_via_provider(selected_model, messages, tools, options)
            else:
                if self.ollama_client is None and ollama is None:
                    raise RuntimeError("Ollama provider selected but ollama client is unavailable")
                response = self._call_ollama_chat(kwargs)
            if trace_id:
                latency_trace.mark(
                    trace_id,
                    "llm.response",
                    {"model": selected_model, "duration_ms": round((time.monotonic() - started) * 1000.0, 2)},
                )
            return response
        except Exception as exc:
            fallback = str(getattr(self, "clm_fallback_model", "") or "").strip()
            if (
                getattr(self, "llm_provider", "ollama") == "ollama"
                and getattr(self, "clm_fallback_enabled", False)
                and getattr(self, "fallback_on_error", False)
                and fallback
                and fallback != selected_model
            ):
                logger.warning("Primary model '%s' failed (%s). Retrying with fallback '%s'.", selected_model, exc, fallback)
                kwargs["model"] = fallback
                response = self._call_ollama_chat(kwargs)
                if trace_id:
                    latency_trace.mark(trace_id, "llm.response", {"model": fallback, "fallback": True})
                return response
            if trace_id:
                latency_trace.mark(trace_id, "llm.error", {"detail": repr(exc)})
            raise

    def _chat_maybe_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        options: Optional[Dict[str, Any]],
        on_sentence: Optional[Callable[[str, int], None]] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not (
            on_sentence
            and self.persona_stream_enabled
            and self.llm_provider == "ollama"
            and self.ollama_client is not None
        ):
            return self._chat(model, messages, tools, options, trace_id=trace_id)

        import re as _re

        if AgentOrchestrator._SENTENCE_END_RE is None:
            AgentOrchestrator._SENTENCE_END_RE = _re.compile(r"(?<=[.!?…])\s+")
        selected_model = self._pick_runtime_model(model)
        kwargs: Dict[str, Any] = {"model": selected_model, "messages": messages, "stream": True}
        if tools is not None:
            kwargs["tools"] = tools
        if options is not None:
            kwargs["options"] = options

        started = time.monotonic()
        if trace_id:
            latency_trace.mark(trace_id, "llm.request", {"model": selected_model, "stream": True})
        try:
            stream = self._call_ollama_chat(kwargs)
        except Exception as exc:
            logger.warning("Streaming chat failed, falling back to blocking: %s", exc)
            return self._chat(model, messages, tools, options, trace_id=trace_id)

        buffer = ""
        pieces: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        sentence_index = 0
        first_token = True
        for chunk in stream:
            message = chunk.get("message", {}) or {}
            chunk_tools = message.get("tool_calls")
            if chunk_tools:
                tool_calls.extend(chunk_tools)
            piece = str(message.get("content", ""))
            if not piece:
                continue
            if first_token and trace_id:
                first_token = False
                latency_trace.mark(
                    trace_id,
                    "llm.first_token",
                    {"duration_ms": round((time.monotonic() - started) * 1000.0, 2)},
                )
            pieces.append(piece)
            if tool_calls:
                continue
            buffer += piece
            while True:
                match = AgentOrchestrator._SENTENCE_END_RE.search(buffer)
                if not match:
                    break
                sentence = buffer[: match.end()].strip()
                buffer = buffer[match.end() :]
                if sentence:
                    if trace_id:
                        latency_trace.mark(trace_id, "llm.sentence", {"index": sentence_index, "chars": len(sentence)})
                    on_sentence(sentence, sentence_index)
                    sentence_index += 1

        full_content = "".join(pieces).strip()
        if not tool_calls and buffer.strip():
            sentence = buffer.strip()
            if trace_id:
                latency_trace.mark(trace_id, "llm.sentence", {"index": sentence_index, "chars": len(sentence)})
            on_sentence(sentence, sentence_index)
        if trace_id:
            latency_trace.mark(
                trace_id,
                "llm.response",
                {"model": selected_model, "duration_ms": round((time.monotonic() - started) * 1000.0, 2)},
            )
        return {"message": {"content": full_content, "tool_calls": tool_calls}} if tool_calls else {"message": {"content": full_content}}

    _SENTENCE_END_RE = None  # compiled lazily below

    def _stream_chat_sentences(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Dict[str, Any],
        on_sentence: Callable[[str, int], None],
    ) -> str:
        """Stream an Ollama chat and emit complete sentences as they arrive.

        Returns the full response text. Raises on transport errors so the
        caller can fall back to the blocking path.
        """
        import re as _re

        if AgentOrchestrator._SENTENCE_END_RE is None:
            AgentOrchestrator._SENTENCE_END_RE = _re.compile(r"(?<=[.!?…])\s+")
        sent_re = AgentOrchestrator._SENTENCE_END_RE

        stream = self._call_ollama_chat(
            {"model": model, "messages": messages, "options": options, "stream": True}
        )
        buffer = ""
        pieces: List[str] = []
        idx = 0
        for chunk in stream:
            piece = str((chunk.get("message", {}) or {}).get("content", ""))
            if not piece:
                continue
            pieces.append(piece)
            buffer += piece
            while True:
                match = sent_re.search(buffer)
                if not match:
                    break
                sentence = buffer[: match.end()].strip()
                buffer = buffer[match.end():]
                if sentence:
                    try:
                        on_sentence(sentence, idx)
                    except Exception:
                        logger.debug("on_sentence callback failed", exc_info=True)
                    idx += 1
        tail = buffer.strip()
        if tail:
            try:
                on_sentence(tail, idx)
            except Exception:
                logger.debug("on_sentence callback failed", exc_info=True)
        return "".join(pieces).strip()

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

    def _run_native_history_loop(
        self,
        active_model: str,
        messages: List[Dict[str, Any]],
        actions_out: Optional[List[Dict[str, Any]]] = None,
        *,
        num_predict: Optional[int] = None,
        on_sentence: Optional[Callable[[str, int], None]] = None,
        max_steps: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> Tuple[str, int]:
        tools = self.tool_registry.get_tool_schema()
        final_text = ""
        steps_used = 0
        predict_budget = int(num_predict if num_predict is not None else self.chat_num_predict)
        step_limit = max(1, int(max_steps if max_steps is not None else self.max_steps))

        for step_index in range(step_limit):
            steps_used = step_index + 1
            try:
                response = self._chat_maybe_stream(
                    active_model,
                    messages,
                    tools,
                    {"temperature": self.temperature, "num_ctx": self.num_ctx, "num_predict": predict_budget},
                    on_sentence=on_sentence,
                    trace_id=trace_id,
                )
            except Exception as exc:
                logger.error("LLM tool loop crashed: %s", exc)
                final_text = "System fault during cognitive cycle."
                break

            message = response.get("message", {})
            messages.append(message)
            tool_calls = message.get("tool_calls")
            if tool_calls:
                self._append_history("assistant", message.get("content", ""), tool_calls=tool_calls)
                for tool in tool_calls:
                    fn_name = str(tool.get("function", {}).get("name", ""))
                    fn_args = self._extract_tool_arguments(tool.get("function", {}).get("arguments", {}))
                    if trace_id:
                        latency_trace.mark(trace_id, "tool.start", {"tool": fn_name, "step": steps_used})
                    tool_result = self.tool_registry.execute(fn_name, fn_args)
                    if trace_id:
                        latency_trace.mark(trace_id, "tool.done", {"tool": fn_name, "step": steps_used})
                    if actions_out is not None:
                        actions_out.append({"tool": fn_name, "args": fn_args, "result": str(tool_result)[:200]})
                    messages.append({"role": "tool", "content": tool_result, "name": fn_name})
                    self._append_history("tool", tool_result, tool_name=fn_name)
                continue

            final_text = str(message.get("content", ""))
            self._append_history("assistant", final_text)
            break

        if not final_text:
            final_text = "Task completed using internal tools."
        return final_text, steps_used

    @staticmethod
    def _enqueue_sentences(text: str, on_sentence: Callable[[str, int], None]) -> None:
        import re
        parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", str(text or "").strip()) if p.strip()]
        if not parts:
            parts = [str(text or "").strip()]
        for idx, sentence in enumerate(parts):
            if sentence:
                try:
                    on_sentence(sentence, idx)
                except Exception:
                    logger.debug("on_sentence callback failed", exc_info=True)

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
        executed_actions: List[Dict[str, Any]] = []
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
                executed_actions.append(
                    {
                        "tool": fn_name,
                        "args": fn_args,
                        "result": str(tool_result_str)[:200],
                    }
                )
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
            "actions": executed_actions,
            "steps": steps_taken,
        }

    def _synthesize_main_persona(
        self,
        user_prompt: str,
        reports: List[Dict[str, Any]],
        survival_override: Optional[str],
        active_model: str,
        session_language: Optional[str] = None,
        on_sentence: Optional[Callable[[str, int], None]] = None,
    ) -> str:
        # MARK: Layer-3 is the only layer that speaks as the main persona.
        # Use configurable persona system prompt when provided; otherwise use a neutral default
        try:
            from modules.common.system_prompts import persona_prompt_with_language
        except Exception:
            persona_prompt_with_language = None
        lang_rule = self._language_directive(session_language)
        if persona_prompt_with_language is not None:
            system_prompt = persona_prompt_with_language(self.persona_system_prompt, lang_rule)
        else:
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
        actions_taken = self._summarize_actions(reports)
        user_payload = {
            "request": user_prompt,
            "safety_override": survival_override or "",
            "subagent_reports": compact_reports,
        }
        if actions_taken:
            # Let the persona speak consistently with what physically happened
            # ("I turned the lights red") instead of ignoring executed tools.
            user_payload["actions_taken"] = actions_taken

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
        ]
        adaptive_persona_np = self._adaptive_persona_num_predict(user_prompt=user_prompt, report_count=len(compact_reports))
        options = {
            "temperature": self.temperature,
            "num_ctx": self.num_ctx,
            "num_predict": adaptive_persona_np,
        }

        # Streaming path: sentences reach TTS while the model is still writing.
        if (
            on_sentence is not None
            and self.persona_stream_enabled
            and self.llm_provider == "ollama"
            and self.ollama_client is not None
        ):
            try:
                streamed = self._stream_chat_sentences(
                    self._pick_runtime_model(active_model), messages, options, on_sentence,
                )
                if streamed:
                    return streamed
            except Exception as exc:
                logger.warning("Persona streaming failed, falling back to blocking chat: %s", exc)

        try:
            response = self._chat(
                model=active_model,
                messages=messages,
                options=options,
            )
            final_text = str(response.get("message", {}).get("content", "")).strip()
            if final_text:
                return final_text
        except Exception as exc:
            logger.warning("Main persona synthesis failed: %s", exc)

        if reports:
            return str(reports[0].get("text", ""))
        return "Task completed using internal tools."

    @staticmethod
    def _summarize_actions(reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flatten executed tool calls from sub-agent reports for persona/API output."""
        summary: List[Dict[str, Any]] = []
        for r in reports:
            if not isinstance(r, dict):
                continue
            for action in r.get("actions") or []:
                if not isinstance(action, dict):
                    continue
                summary.append(
                    {
                        "tool": str(action.get("tool", "")),
                        "args": action.get("args", {}),
                        "result": str(action.get("result", ""))[:160],
                    }
                )
        return summary

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
        """Keep the detected ISO code as-is (2 letters); default is Turkish.

        The language list is not hardcoded here: any code flows through to the
        LLM directive and the TTS layer, which pick their own fallbacks.
        """
        raw = str(language or "tr").strip().lower()
        code = raw.split("-")[0].split("_")[0][:2]
        return code if len(code) == 2 and code.isalpha() else "tr"

    @classmethod
    def _language_directive(cls, language: Optional[str]) -> str:
        lang = cls._normalize_session_language(language)
        lang_name = ""
        try:
            from .progress import _load_catalog

            entry = _load_catalog().get("languages", {}).get(lang)
            if isinstance(entry, dict):
                lang_name = str(entry.get("name", "")).strip()
        except Exception:
            lang_name = ""
        label = lang_name or f"the language with ISO code '{lang}'"
        return (
            f"The user is speaking {label} (ISO code: {lang}). "
            f"Reply ONLY in that language. Do not mix in other languages."
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

    def _build_progress_callback(self, progress_token: str, progress_cb: Optional[Callable] = None) -> Callable:
        def _unified_progress_cb(event: Dict[str, Any]) -> None:
            event["token"] = progress_token
            self.progress_manager.on_progress_event(event)
            if progress_cb:
                try:
                    progress_cb(event)
                except Exception:
                    pass
        return _unified_progress_cb

    def _should_fast_path(self, user_prompt: str, *, native_tools: bool = False) -> bool:
        """Short prompts (or voice path) skip tri-layer: one native loop with full tools.

        ``native_tools=True`` is set for autonomy speech so the LLM interprets
        commands in any language without keyword-router hardcoding.
        """
        if native_tools:
            return True
        if not self.fast_path_enabled:
            return False
        return len(str(user_prompt or "").strip()) <= self.fast_path_max_chars

    def _native_loop_messages(self, session_language: str) -> List[Dict[str, Any]]:
        try:
            from modules.common.system_prompts import persona_prompt_with_language
        except Exception:
            persona_prompt_with_language = None
        lang_rule = self._language_directive(session_language)
        if persona_prompt_with_language is not None:
            system_prompt = persona_prompt_with_language(self.persona_system_prompt, lang_rule)
        else:
            persona = self.persona_system_prompt or (
                "You are the robot's single response layer. Answer the user directly."
            )
            system_prompt = (
                f"{persona}\n\n{lang_rule}\n\n"
                "You understand the user in any language. Interpret intent across languages "
                "(e.g. LED color, emotion, speak, head movement) and call the matching tool.\n"
                "You can control the robot with the available tools (lights, emotion, "
                "speech, head, sounds...). When the user asks for a physical action, "
                "call the matching tool instead of only describing it, then confirm "
                "briefly in one sentence in the user's language."
            )
        return [{"role": "system", "content": system_prompt}] + list(self.chat_history)

    def _check_provider_availability(self) -> Optional[Dict[str, Any]]:
        if self.llm_provider == "ollama" and not ollama:
            logger.error("Ollama library not found. Native tool loop requires 'ollama' package.")
            return {"text": "System Error: Missing ollama backend."}
        if self.llm_provider != "ollama" and self.provider_client is None:
            logger.error("Provider '%s' selected but provider client is unavailable.", self.llm_provider)
            return {"text": "System Error: Missing provider client backend."}
        return None

    def _run_tri_layer(self, user_prompt: str, world_context: str, survival_override: str,
                       active_model: str, session_language: str,
                       progress_token: str, cb: Callable,
                       on_sentence: Optional[Callable[[str, int], None]] = None) -> tuple[str, int, list]:
        self.last_routed_subagents = self.router.route(user_prompt)
        logger.info("Tri-layer route selected: %s", self.last_routed_subagents)

        plan_summary = self._build_plan_summary(user_prompt, self.last_routed_subagents)
        self.progress_manager.emit_plan(progress_token, plan_summary)
        self._emit_progress(cb, {"type": "plan", "plan": plan_summary})

        subagent_reports: list = []
        total_steps = 0
        if self.last_routed_subagents:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(self.last_routed_subagents), self.subagent_workers)) as ex:
                futures = {}
                for module_name in self.last_routed_subagents:
                    profile = self.subagent_profiles.get(module_name)
                    if not profile:
                        continue
                    fut = ex.submit(self._run_subagent, profile, user_prompt, world_context, survival_override, active_model, cb)
                    futures[fut] = module_name
                for fut in concurrent.futures.as_completed(futures):
                    try:
                        report = fut.result()
                    except Exception as exc:
                        self._safe_log_warning("Sub-agent %s failed in executor: %s", futures.get(fut), exc)
                        continue
                    subagent_reports.append(report)
                    total_steps += int(report.get("steps", 0))

        final_text, total_steps = self._synthesize_from_reports(
            subagent_reports, user_prompt, survival_override, active_model,
            session_language, cb, total_steps, on_sentence=on_sentence,
        )
        return final_text, total_steps, subagent_reports

    def _synthesize_from_reports(self, subagent_reports: list, user_prompt: str,
                                  survival_override: str, active_model: str,
                                  session_language: str, cb: Callable,
                                  total_steps: int,
                                  on_sentence: Optional[Callable[[str, int], None]] = None) -> tuple[str, int]:
        if not subagent_reports:
            messages = list(self.chat_history)
            native_actions: List[Dict[str, Any]] = []
            final_text, steps = self._run_native_history_loop(active_model, messages, actions_out=native_actions)
            if native_actions:
                subagent_reports.append({"module": "native", "text": final_text, "tools": [a["tool"] for a in native_actions], "actions": native_actions, "steps": steps})
            return final_text, steps

        try:
            from modules.ollama.services.clients import GoogleAIStudioClient
            gemini_limited = GoogleAIStudioClient.is_rate_limited(str(getattr(self.provider_client, "api_key", "")))
        except Exception:
            gemini_limited = False

        if gemini_limited:
            from .progress import _msg

            final_text = _msg(
                session_language,
                "quota_exhausted",
                "AI quota is exhausted right now. Can you try again in a minute or two?",
            )
            self._append_history("assistant", final_text)
            return final_text, total_steps

        self._emit_progress(cb, {"type": "persona_start"})
        final_text = self._synthesize_main_persona(
            user_prompt=user_prompt, reports=subagent_reports,
            survival_override=survival_override, active_model=active_model,
            session_language=session_language, on_sentence=on_sentence,
        )
        self._append_history("assistant", final_text)
        return final_text, total_steps

    def step(
        self,
        user_prompt: str = "",
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        native_tools: bool = False,
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        if now - self.last_run < self.cooldown or self.is_busy or not user_prompt:
            return None
        self.last_run = now
        self.is_busy = True

        if speaker and str(speaker).strip().lower() not in {"unknown", "none", ""}:
            try:
                self.world_state.update_state({"speaker": str(speaker).strip()})
            except Exception:
                pass

        previous_hook = self.tool_registry.status_hook
        trace_id = latency_trace.ensure(trace_id, {"component": "agent_core", "language": language or ""})
        latency_trace.mark(trace_id, "agent.request", {"chars": len(user_prompt), "native_tools": native_tools})

        autonomy_client = getattr(self, "autonomy_client", None)
        if autonomy_client and hasattr(autonomy_client, "set_expression_event"):
            try:
                autonomy_client.set_expression_event("agent.thinking", {"trace_id": trace_id})
            except Exception:
                pass

        session_language = self._normalize_session_language(language)
        progress_token = self.progress_manager.new_request(language=session_language)
        self._active_progress_token = progress_token
        callback = self._build_progress_callback(progress_token, progress_cb)
        self.tool_registry.status_hook = callback

        try:
            use_fast_path = self._should_fast_path(user_prompt, native_tools=native_tools)
            self.progress_manager.emit_ack(progress_token, speak=not use_fast_path)
            latency_trace.mark(trace_id, "agent.context_start")
            survival_override = self.check_survival_drives()
            world_context = self.world_state.inject_world_state("")
            memory_context = self._get_world_memory_context(user_prompt)
            if memory_context:
                world_context = f"{world_context}\n\n[World Memory]\n{memory_context}"
            language_rule = self._language_directive(session_language)
            full_prompt = f"{user_prompt}\n\n[{language_rule}]\n\n[World State]\n{world_context}"
            if survival_override:
                full_prompt += f"\n\n{survival_override}"
            self._append_history("user", full_prompt)
            active_model = self._get_active_persona_model()
            latency_trace.mark(trace_id, "agent.context_done", {"model": active_model})

            provider_error = self._check_provider_availability()
            if provider_error:
                latency_trace.finish(trace_id, "provider_unavailable")
                return {**provider_error, "trace_id": trace_id}

            final_text = ""
            total_steps = 0
            subagent_reports: List[Dict[str, Any]] = []
            executed_actions: List[Dict[str, Any]] = []
            stream_state = {"spoken": 0}
            on_sentence: Optional[Callable[[str, int], None]] = None
            if self.speech_arbiter._speak_fn is not None:
                def speak_sentence(sentence: str, index: int) -> None:
                    item_id = self.speech_arbiter.enqueue_final_chunk(
                        sentence,
                        index=index,
                        language=session_language,
                        trace_id=trace_id,
                    )
                    if item_id:
                        stream_state["spoken"] += 1
                on_sentence = speak_sentence

            if self.tri_layer_enabled and not use_fast_path:
                final_text, total_steps, subagent_reports = self._run_tri_layer(
                    user_prompt,
                    world_context,
                    survival_override,
                    active_model,
                    session_language,
                    progress_token,
                    callback,
                    on_sentence=on_sentence,
                )
                executed_actions = self._summarize_actions(subagent_reports)
            else:
                messages = self._native_loop_messages(session_language)
                final_text, total_steps = self._run_native_history_loop(
                    active_model,
                    messages,
                    actions_out=executed_actions,
                    num_predict=getattr(self, "fast_path_num_predict", None) if use_fast_path else None,
                    on_sentence=on_sentence,
                    max_steps=(
                        getattr(self, "fast_path_max_steps", 2)
                        if use_fast_path
                        else getattr(self, "max_steps", 4)
                    ),
                    trace_id=trace_id,
                )

            self.progress_manager.emit_final(progress_token)
            self.memory.remember("dialogue", f"User: {user_prompt} | Bot: {final_text}")
            try:
                self._observe_world_memory_dialogue(user_prompt, final_text)
            except Exception:
                logger.debug("world memory dialogue observation failed", exc_info=True)
            try:
                self.memory_consolidator.consolidate(user_prompt, speaker=self._current_speaker())
            except Exception:
                logger.debug("memory consolidation failed", exc_info=True)

            latency_trace.mark(
                trace_id,
                "agent.done",
                {"steps": total_steps, "speech_handled": stream_state["spoken"] > 0},
            )
            if self.speech_arbiter._speak_fn is None:
                latency_trace.finish(trace_id, "done")
            return {
                "text": final_text,
                "thoughts": f"Agent executed {total_steps} internal steps.",
                "actions": executed_actions,
                "plan": [],
                "route": self.last_routed_subagents,
                "subagents": subagent_reports,
                "speech_handled": stream_state["spoken"] > 0,
                "trace_id": trace_id,
                "latency": latency_trace.get(trace_id),
            }
        except Exception as exc:
            latency_trace.finish(trace_id, "failed", {"detail": repr(exc)})
            raise
        finally:
            self.progress_manager.emit_final(progress_token)
            self.tool_registry.status_hook = previous_hook
            self._active_progress_token = ""
            self.is_busy = False

    def step_event(
        self,
        event_type: str,
        event_prompt: str,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Event-driven step that bypasses cooldown and empty-prompt checks.

        Used by autonomy brain for spontaneous reactions (sound, vision, boredom).
        """
        trace_id = latency_trace.ensure(trace_id, {"component": "agent_core", "event": event_type})
        latency_trace.mark(trace_id, "agent.event_request", {"event": event_type, "chars": len(event_prompt)})

        session_language = self._normalize_session_language(language)
        progress_token = self.progress_manager.new_request(language=session_language)
        self._active_progress_token = progress_token
        callback = self._build_progress_callback(progress_token, None)
        self.tool_registry.status_hook = callback

        try:
            autonomy_client = getattr(self, "autonomy_client", None)
            if autonomy_client and hasattr(autonomy_client, "set_expression_event"):
                try:
                    autonomy_client.set_expression_event(f"agent.event.{event_type}", {"trace_id": trace_id})
                except Exception:
                    pass

            use_fast_path = self._should_fast_path(event_prompt, native_tools=True)
            self.progress_manager.emit_ack(progress_token, speak=not use_fast_path)
            latency_trace.mark(trace_id, "agent.context_start")
            survival_override = self.check_survival_drives()
            world_context = self.world_state.inject_world_state("")
            memory_context = self._get_world_memory_context(event_prompt)
            if memory_context:
                world_context = f"{world_context}\n\n[World Memory]\n{memory_context}"
            language_rule = self._language_directive(session_language)
            full_prompt = f"{event_prompt}\n\n[{language_rule}]\n\n[World State]\n{world_context}"
            if survival_override:
                full_prompt += f"\n\n{survival_override}"
            self._append_history("user", full_prompt)
            active_model = self._get_active_persona_model()
            latency_trace.mark(trace_id, "agent.context_done", {"model": active_model})

            provider_error = self._check_provider_availability()
            if provider_error:
                latency_trace.finish(trace_id, "provider_unavailable")
                return {**provider_error, "trace_id": trace_id}

            final_text = ""
            total_steps = 0
            subagent_reports: List[Dict[str, Any]] = []
            executed_actions: List[Dict[str, Any]] = []
            stream_state = {"spoken": 0}
            on_sentence: Optional[Callable[[str, int], None]] = None
            if self.speech_arbiter._speak_fn is not None:
                def speak_sentence(sentence: str, index: int) -> None:
                    item_id = self.speech_arbiter.enqueue_final_chunk(
                        sentence,
                        index=index,
                        language=session_language,
                        trace_id=trace_id,
                    )
                    if item_id:
                        stream_state["spoken"] += 1
                on_sentence = speak_sentence

            if self.tri_layer_enabled and not use_fast_path:
                final_text, total_steps, subagent_reports = self._run_tri_layer(
                    event_prompt,
                    world_context,
                    survival_override,
                    active_model,
                    session_language,
                    progress_token,
                    callback,
                    on_sentence=on_sentence,
                )
                executed_actions = self._summarize_actions(subagent_reports)
            else:
                messages = self._native_loop_messages(session_language)
                final_text, total_steps = self._run_native_history_loop(
                    active_model,
                    messages,
                    actions_out=executed_actions,
                    num_predict=getattr(self, "fast_path_num_predict", None) if use_fast_path else None,
                    on_sentence=on_sentence,
                    max_steps=(
                        getattr(self, "fast_path_max_steps", 2)
                        if use_fast_path
                        else getattr(self, "max_steps", 4)
                    ),
                    trace_id=trace_id,
                )

            self.progress_manager.emit_final(progress_token)
            self.memory.remember("dialogue", f"Event({event_type}): {event_prompt} | Bot: {final_text}")
            try:
                self._observe_world_memory_dialogue(event_prompt, final_text)
            except Exception:
                logger.debug("world memory dialogue observation failed", exc_info=True)
            try:
                self.memory_consolidator.consolidate(event_prompt, speaker=self._current_speaker())
            except Exception:
                logger.debug("memory consolidation failed", exc_info=True)

            latency_trace.mark(
                trace_id,
                "agent.done",
                {"steps": total_steps, "speech_handled": stream_state["spoken"] > 0},
            )
            if self.speech_arbiter._speak_fn is None:
                latency_trace.finish(trace_id, "done")
            return {
                "text": final_text,
                "thoughts": f"Agent reacted to {event_type} in {total_steps} internal steps.",
                "actions": executed_actions,
                "plan": [],
                "route": self.last_routed_subagents,
                "subagents": subagent_reports,
                "speech_handled": stream_state["spoken"] > 0,
                "trace_id": trace_id,
                "latency": latency_trace.get(trace_id),
            }
        except Exception as exc:
            latency_trace.finish(trace_id, "failed", {"detail": repr(exc)})
            raise
        finally:
            self.progress_manager.emit_final(progress_token)
            self.tool_registry.status_hook = None
            self._active_progress_token = ""

