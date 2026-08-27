from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .agent_context import AgentContextMixin
from .agent_turn import AgentTurnMixin
from modules.common.latency_trace import latency_trace
from modules.common.model_policy import get_model_policy  # type: ignore

logger = logging.getLogger("agent.orchestrator")


class AgentOrchestrator(AgentContextMixin, AgentTurnMixin):
    """LLM turn orchestrator invoked by autonomy. Does not own the life loop.

    Autonomy decides whether to act; this class runs one tool-calling turn.
    See `.sentrybot/context/behavior-authority.md`.
    """

    def __init__(self, config: dict, autonomy_client=None):
        self.config = config
        self.autonomy_client = autonomy_client
        if hasattr(self, "_warn_insecure_defaults"):
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
        self._turn_lock = threading.Lock()

    def start(self) -> None:
        """Start background subsystems."""
        self.sensor_loop.start()
        self.idle_system.start()
        self.speech_arbiter.start()
        logger.info("AgentOrchestrator subsystems started.")

    def stop(self) -> None:
        self.sensor_loop.stop()
        self.idle_system.stop()
        self.speech_arbiter.stop()
        logger.info("AgentOrchestrator subsystems stopped.")


    def _try_enter_turn(self, prompt: str, *, bypass_cooldown: bool = False) -> bool:
        """Enter one agent turn if no other turn is active."""
        if not prompt:
            return False
        if not self._turn_lock.acquire(blocking=False):
            return False
        now = time.time()
        if self.is_busy or (not bypass_cooldown and now - self.last_run < self.cooldown):
            self._turn_lock.release()
            return False
        if not bypass_cooldown:
            self.last_run = now
        self.is_busy = True
        return True

    def _exit_turn(self) -> None:
        """Leave the active agent turn and release the turn lock."""
        self.is_busy = False
        try:
            self._turn_lock.release()
        except RuntimeError:
            logger.debug("agent turn lock release requested while unlocked", exc_info=True)

    def check_survival_drives(self) -> Optional[str]:
        """Overrides logic if critical limits are reached."""
        bat = self.world_state.get_state().get("battery_percent", 100)
        if bat < 15:
            logger.warning("SURVIVAL DRIVE: Low Battery (%s%%)!", bat)
            return "[CRITICAL] Battery is severely low. Do not engage in lengthy tasks. Find a charger or warn the user."
        return None

    def _append_history(self, role: str, content: str, tool_calls=None, tool_name=None) -> None:
        msg = {"role": role, "content": content}
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_name is not None:
            msg["name"] = tool_name

        self.chat_history.append(msg)
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
        """Resolve the model for the native tool loop using centralized model policy."""
        policy = get_model_policy()
        resolved = policy.resolve_model(self.config)
        return str(resolved.get("model", self.model))

    def step(
        self,
        user_prompt: str = "",
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        native_tools: bool = False,
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self._try_enter_turn(user_prompt, bypass_cooldown=False):
            return None

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
                    chunk_lang = session_language
                    try:
                        from modules.voice.speak.services.lang_detect import detect_text_language
                        chunk_lang = detect_text_language(sentence, default=session_language)
                    except Exception:
                        pass
                    item_id = self.speech_arbiter.enqueue_final_chunk(
                        sentence,
                        index=index,
                        language=chunk_lang,
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
            self._exit_turn()

    def step_event(
        self,
        event_type: str,
        event_prompt: str,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Event-driven step that bypasses cooldown but not active-turn safety."""
        if not self._try_enter_turn(event_prompt, bypass_cooldown=True):
            return None
        previous_hook = self.tool_registry.status_hook

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
            self.tool_registry.status_hook = previous_hook
            self._active_progress_token = ""
            self._exit_turn()


# sentrybot_batch06g_agent_step_speaker_bridge_guard
try:
    _sentrybot_batch06g_prev_agent_step = AgentOrchestrator.step

    def _sentrybot_batch06g_agent_step(self, *args, **kwargs):
        speaker = kwargs.get("speaker")

        if speaker is None and len(args) >= 2:
            speaker = args[1]

        if speaker:
            try:
                world_state = getattr(self, "world_state", None)

                if world_state is not None:
                    state = getattr(world_state, "state", None)

                    if isinstance(state, dict):
                        state["speaker"] = speaker
                    elif hasattr(world_state, "set"):
                        world_state.set("speaker", speaker)

            except Exception:
                pass

        return _sentrybot_batch06g_prev_agent_step(self, *args, **kwargs)

    AgentOrchestrator.step = _sentrybot_batch06g_agent_step

except NameError:
    pass


# sentrybot_batch06j_agent_turn_lock_lazy_guard
try:
    _sentrybot_batch06j_prev_try_enter_turn = AgentOrchestrator._try_enter_turn

    def _sentrybot_batch06j_try_enter_turn(self, *args, **kwargs):
        try:
            if getattr(self, "_turn_lock", None) is None:
                import threading
                self._turn_lock = threading.Lock()

            if not hasattr(self, "is_busy"):
                self.is_busy = False

            if not hasattr(self, "last_run"):
                self.last_run = 0

            if not hasattr(self, "cooldown"):
                self.cooldown = 0

        except Exception:
            pass

        return _sentrybot_batch06j_prev_try_enter_turn(self, *args, **kwargs)

    AgentOrchestrator._try_enter_turn = _sentrybot_batch06j_try_enter_turn

except NameError:
    pass

try:
    _sentrybot_batch06j_prev_exit_turn = AgentOrchestrator._exit_turn

    def _sentrybot_batch06j_exit_turn(self, *args, **kwargs):
        try:
            if getattr(self, "_turn_lock", None) is None:
                import threading
                self._turn_lock = threading.Lock()
        except Exception:
            pass

        return _sentrybot_batch06j_prev_exit_turn(self, *args, **kwargs)

    AgentOrchestrator._exit_turn = _sentrybot_batch06j_exit_turn

except NameError:
    pass
except AttributeError:
    pass

