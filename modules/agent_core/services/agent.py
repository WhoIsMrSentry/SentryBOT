from __future__ import annotations

from contextlib import contextmanager
import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from .agent_context import AgentContextMixin
from .agent_turn import AgentTurnMixin
from modules.common.latency_trace import latency_trace
from modules.common.model_policy import get_model_policy  # type: ignore
from modules.common.model_roles import (
    ROLE_CHAT,
    explicit_single_model_mode,
    infer_prompt_role,
    resolve_role_model,
)
from .laya_action_contract import bind_laya_action_proposal

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
        self._ack_tls = threading.local()
        if getattr(self, "_history_lock", None) is None:
            self._history_lock = threading.RLock()

    @contextmanager
    def suppress_ack(self) -> Iterator[None]:
        """Suppress immediate spoken ack fillers for autonomous background turns."""
        tls = getattr(self, "_ack_tls", None)
        if tls is None:
            tls = threading.local()
            self._ack_tls = tls
        prev = int(getattr(tls, "depth", 0) or 0)
        tls.depth = prev + 1
        try:
            yield
        finally:
            tls.depth = prev

    def _is_ack_suppressed(self) -> bool:
        tls = getattr(self, "_ack_tls", None)
        return bool(tls is not None and int(getattr(tls, "depth", 0) or 0) > 0)

    def start(self) -> None:
        """Start background subsystems."""
        self._stopped_once = False
        self.sensor_loop.start()
        self.idle_system.start()
        self.speech_arbiter.start()
        self._start_runtime_warmup_async()
        logger.info("AgentOrchestrator subsystems started.")

    def _start_runtime_warmup_async(self) -> None:
        """Pre-warm System 1 ONNX and keep primary Ollama model resident in VRAM."""
        import os

        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        if getattr(self, "_warmup_started", False):
            return
        self._warmup_started = True

        def _warmup() -> None:
            try:
                from .laya_engine import LayaEngine

                engine = LayaEngine.get_instance()
                if engine is not None and getattr(engine, "enabled", True):
                    engine.decide("merhaba")
            except Exception as exc:
                logger.debug("System 1 warmup skipped: %s", exc)
            try:
                from modules.common.model_roles import DEFAULT_CHAT_MODEL
                from .ollama_compat import call_ollama_chat

                client = getattr(self, "ollama_client", None)
                if client is not None and self._is_real_ollama_client(client):
                    call_ollama_chat(
                        client,
                        model=getattr(self, "model", None) or DEFAULT_CHAT_MODEL,
                        messages=[{"role": "user", "content": "hazır"}],
                        options={
                            "num_predict": 1,
                            "num_ctx": int(getattr(self, "num_ctx", 8192) or 8192),
                            "temperature": 0.0,
                        },
                        think=False,
                        keep_alive=getattr(self, "ollama_keep_alive", -1),
                    )
                    self._ollama_probe_ok_until = time.monotonic() + 60.0
            except Exception as exc:
                logger.debug("Ollama warmup skipped: %s", exc)

        threading.Thread(target=_warmup, name="agent-runtime-warmup", daemon=True).start()

    def stop(self) -> None:
        if getattr(self, "_stopped_once", False):
            return
        self._stopped_once = True
        self.sensor_loop.stop()
        self.idle_system.stop()
        self.speech_arbiter.stop()
        if hasattr(self, "_shutdown_memory_consolidator"):
            self._shutdown_memory_consolidator()
        registry = getattr(self, "tool_registry", None)
        if registry is not None and hasattr(registry, "close"):
            try:
                registry.close()
            except Exception:
                pass
        handler_sess = getattr(self, "_handler_http_session", None)
        if handler_sess is not None and hasattr(handler_sess, "close"):
            try:
                handler_sess.close()
            except Exception:
                pass
        goal_store = getattr(self, "goal_store", None)
        if goal_store is not None and hasattr(goal_store, "close"):
            try:
                goal_store.close()
            except Exception:
                pass
        logger.info("AgentOrchestrator subsystems stopped.")


    def _try_enter_turn(self, prompt: str, *, bypass_cooldown: bool = False) -> bool:
        """Enter one agent turn if no other turn is active."""
        if getattr(self, "_turn_lock", None) is None:
            self._turn_lock = threading.Lock()
        if not hasattr(self, "is_busy"):
            self.is_busy = False
        if not hasattr(self, "last_run"):
            self.last_run = 0.0
        if not hasattr(self, "cooldown"):
            self.cooldown = 0.0
        if not prompt:
            return False
        acquired = (
            self._turn_lock.acquire(timeout=1.5)
            if bypass_cooldown
            else self._turn_lock.acquire(blocking=False)
        )
        if not acquired:
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
        if getattr(self, "_turn_lock", None) is None:
            self._turn_lock = threading.Lock()
        self.is_busy = False
        try:
            self._turn_lock.release()
        except RuntimeError:
            logger.debug("agent turn lock release requested while unlocked", exc_info=True)

    def _current_speech_tone(self) -> Optional[Dict[str, Any]]:
        """Take one safe mood snapshot for every spoken chunk in this turn."""
        mood_manager = getattr(self, "mood_manager", None)
        get_tone = getattr(mood_manager, "get_speech_tone", None)
        if not callable(get_tone):
            return None
        try:
            tone = get_tone()
            return dict(tone) if isinstance(tone, dict) and tone else None
        except Exception:
            logger.debug("Could not resolve mood-aware speech tone", exc_info=True)
            return None

    def _record_laya_latency(self, trace_id: str) -> None:
        """Keep System 1 time separate from model TTFT in the turn trace."""
        decision = getattr(self, "_last_laya_fast_path_decision", None)
        if decision is None:
            return
        try:
            latency_trace.mark(
                trace_id,
                "laya.inference",
                {
                    "inference_ms": max(0.0, float(getattr(decision, "inference_ms", 0.0) or 0.0)),
                    "target_module": str(getattr(decision, "target_module", "") or ""),
                    "urgency": float(getattr(decision, "urgency_score", 0.0) or 0.0),
                },
            )
        except Exception:
            logger.debug("Could not record Laya inference latency", exc_info=True)

    @staticmethod
    def _bind_laya_action_request(decision: Any, request_id: str) -> None:
        """Attach the current internal request ID to an inert Laya proposal."""
        proposal = getattr(decision, "suggested_action", None)
        if proposal is None:
            return
        decision.suggested_action = bind_laya_action_proposal(proposal, request_id)

    def _ensure_history_lock(self) -> threading.RLock:
        lock = getattr(self, "_history_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._history_lock = lock
        return lock

    def _get_history_snapshot(self) -> List[Dict[str, Any]]:
        with self._ensure_history_lock():
            return [dict(m) for m in getattr(self, "chat_history", [])]

    def _append_history(self, role: str, content: str, tool_calls=None, tool_name=None) -> None:
        msg = {"role": role, "content": content}
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_name is not None:
            msg["name"] = tool_name

        with self._ensure_history_lock():
            self.chat_history.append(msg)
            limit = int(getattr(self, "max_history", 10) or 10) * 2
            if len(self.chat_history) > limit:
                self.chat_history = self.chat_history[-limit:]

    def route_preview(self, user_prompt: str) -> Dict[str, Any]:
        modules = self.router.route(user_prompt)
        return {
            "enabled": self.tri_layer_enabled,
            "modules": modules,
            "available": sorted(self.subagent_profiles.keys()),
        }

    def generate_reflection(self, prompt: str) -> Optional[str]:
        """Generate an episodic dream reflection using the configured LLM client."""
        try:
            if getattr(self, "provider_client", None) is not None and hasattr(self.provider_client, "generate_text"):
                return self.provider_client.generate_text(prompt)
            if getattr(self, "ollama_client", None) is not None:
                reflection_model = resolve_role_model(
                    getattr(self, "config", None),
                    "reflection",
                    fallback=self.model,
                )
                resp = self.ollama_client.chat(
                    model=reflection_model,
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.4, "num_ctx": int(getattr(self, "num_ctx", 8192) or 8192)},
                )
                if isinstance(resp, dict):
                    msg = resp.get("message") or {}
                    return str(msg.get("content", "")).strip() or None
                if hasattr(resp, "message") and hasattr(resp.message, "content"):
                    return str(resp.message.content).strip() or None
        except Exception as exc:
            logger.debug("generate_reflection failed: %s", exc)
        return None

    def _get_active_persona_model(self, prompt: str = "") -> str:
        """Resolve the model for the native tool loop using role-aware model policy."""
        cfg = getattr(self, "config", None)
        policy = get_model_policy()
        resolved = policy.resolve_model(cfg)
        default_model = str(resolved.get("model", self.model))
        if explicit_single_model_mode(cfg) is True:
            return default_model
        role = infer_prompt_role(prompt) if prompt else ROLE_CHAT
        if role != ROLE_CHAT:
            return resolve_role_model(cfg, role, prompt=prompt, fallback=default_model)
        return resolve_role_model(cfg, ROLE_CHAT, fallback=default_model)

    def _resolve_turn_laya_decision(self, user_prompt: str, laya_eng: Any) -> Any:
        """Reuse an existing System 1 decision for the current prompt when available."""
        laya_dec = getattr(self, "_last_laya_fast_path_decision", None)
        if laya_dec is not None:
            return laya_dec
        precomputed = getattr(self, "_precomputed_laya_decision", None)
        if isinstance(precomputed, tuple) and len(precomputed) == 2 and precomputed[0] == user_prompt:
            self._last_laya_fast_path_decision = precomputed[1]
            return precomputed[1]
        if (
            getattr(laya_eng, "_last_decision_text", None) == user_prompt
            and getattr(laya_eng, "_last_decision", None) is not None
        ):
            laya_dec = getattr(laya_eng, "_last_decision", None)
            self._last_laya_fast_path_decision = laya_dec
            return laya_dec
        try:
            laya_dec = laya_eng.decide_with_context(
                user_prompt,
                world_state=self.world_state.get_state(),
                visual_context=self.world_state.get_laya_scene_summary(),
            )
        except (AttributeError, TypeError):
            laya_dec = laya_eng.decide(user_prompt)
        self._last_laya_fast_path_decision = laya_dec
        return laya_dec

    def _prepare_turn_context(
        self,
        prompt: str,
        session_language: str,
        trace_id: str,
    ) -> Tuple[Optional[str], str, str]:
        """Build transient world/memory context, append clean user prompt to history, and resolve model."""
        latency_trace.mark(trace_id, "agent.context_start")
        survival_override = self.check_survival_drives()
        world_context = self.world_state.inject_world_state("")
        memory_context = self._get_world_memory_context(prompt)
        if memory_context:
            world_context = f"{world_context}\n\n[World Memory]\n{memory_context}"
        self._append_history("user", prompt)
        try:
            active_model = self._get_active_persona_model(prompt)
        except TypeError:
            active_model = self._get_active_persona_model()
        latency_trace.mark(trace_id, "agent.context_done", {"model": active_model})
        return survival_override, world_context, active_model

    def _bind_speaker(self, speaker: Optional[str]) -> None:
        if not speaker:
            return
        try:
            world_state = getattr(self, "world_state", None)
            if world_state is None:
                return
            state = getattr(world_state, "state", None)
            if isinstance(state, dict):
                state["speaker"] = speaker
            elif hasattr(world_state, "set"):
                world_state.set("speaker", speaker)
            if (
                hasattr(world_state, "update_state")
                and str(speaker).strip().lower() not in {"unknown", "none", ""}
            ):
                world_state.update_state({"speaker": str(speaker).strip()})
        except Exception:
            pass

    def _make_sentence_callback(
        self,
        session_language: str,
        trace_id: str,
        stream_state: Dict[str, int],
    ) -> Optional[Callable[[str, int], None]]:
        arbiter = getattr(self, "speech_arbiter", None)
        if arbiter is None or getattr(arbiter, "_speak_fn", None) is None:
            return None
        speech_tone = self._current_speech_tone()
        detected_lang: Dict[str, Optional[str]] = {"value": None}

        def speak_sentence(sentence: str, index: int) -> None:
            try:
                from modules.ai_provider.services.tags import strip_speech_control_artifacts

                sentence = strip_speech_control_artifacts(sentence)
            except Exception:
                sentence = str(sentence or "").strip()
            if not sentence:
                return
            if detected_lang["value"] is None:
                lang = session_language
                try:
                    from modules.voice.speak.services.lang_detect import detect_text_language

                    lang = detect_text_language(sentence, default=session_language)
                except Exception:
                    pass
                detected_lang["value"] = lang
            chunk_lang = detected_lang["value"] or session_language
            item_id = arbiter.enqueue_final_chunk(
                sentence,
                index=index,
                language=chunk_lang,
                tone=speech_tone,
                trace_id=trace_id,
            )
            if item_id:
                stream_state["spoken"] += 1

        return speak_sentence

    def _finalize_turn_memory(self, prompt: str, final_text: str, dialogue_entry: str) -> None:
        """Record clean assistant reply, episodic dialogue, and world/social memory consolidation."""
        if str(final_text or "").strip():
            self._append_history("assistant", str(final_text))
        self.memory.remember("dialogue", dialogue_entry)
        try:
            self._observe_world_memory_dialogue(prompt, final_text)
        except Exception:
            logger.debug("world memory dialogue observation failed", exc_info=True)
        try:
            self.memory_consolidator.consolidate(prompt, speaker=self._current_speaker())
        except Exception:
            logger.debug("memory consolidation failed", exc_info=True)

    def _try_short_circuit_emotion_command(
        self,
        prompt: str,
        session_language: str,
        event_type: Optional[str],
        executed_actions: List[Dict[str, Any]],
        on_sentence: Optional[Callable[[str, int], None]],
    ) -> Optional[str]:
        """Short-circuit 1-2 word emotion imperatives via System 1 without calling Ollama."""
        if event_type:
            return None
        cfg = getattr(self, "config", None)
        agent_cfg = cfg.get("agent", {}) if isinstance(cfg, dict) and isinstance(cfg.get("agent"), dict) else {}
        explicit_flag = agent_cfg.get("emotion_command_shortcut")
        if explicit_flag is False:
            return None
        if explicit_flag is None and not self._is_real_ollama_client(getattr(self, "ollama_client", None)):
            return None
        try:
            from modules.autonomy.services.brain_parts.speech_react import SpeechReactMixin

            cmd = SpeechReactMixin._emotion_command_for_text(prompt)
            if not cmd:
                return None
            reply_text = SpeechReactMixin._emotion_command_reply(cmd, session_language)
            tool_reg = getattr(self, "tool_registry", None)
            if tool_reg is not None:
                tool_args = {"emotion": cmd, "intensity": 0.85}
                exec_fn = getattr(tool_reg, "execute", None) or getattr(tool_reg, "execute_tool", None)
                if callable(exec_fn):
                    res = exec_fn("express_emotion", tool_args)
                    executed_actions.append({"tool": "express_emotion", "args": tool_args, "result": res})
            if callable(on_sentence) and reply_text:
                on_sentence(reply_text, 0)
            return reply_text
        except Exception as exc:
            logger.debug("Emotion command short-circuit skipped: %s", exc)
            return None

    def _run_turn_core(
        self,
        prompt: str,
        *,
        bypass_cooldown: bool,
        language: Optional[str],
        speaker: Optional[str],
        native_tools: bool,
        trace_id: Optional[str],
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        event_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        self._bind_speaker(speaker)
        if not self._try_enter_turn(prompt, bypass_cooldown=bypass_cooldown):
            return None

        previous_hook = self.tool_registry.status_hook
        meta: Dict[str, Any] = {"component": "agent_core"}
        if event_type:
            meta["event"] = event_type
        else:
            meta["language"] = language or ""
        trace_id = latency_trace.ensure(trace_id, meta)
        if event_type:
            latency_trace.mark(trace_id, "agent.event_request", {"event": event_type, "chars": len(prompt)})
        else:
            latency_trace.mark(trace_id, "agent.request", {"chars": len(prompt), "native_tools": native_tools})

        autonomy_client = getattr(self, "autonomy_client", None)
        if autonomy_client and hasattr(autonomy_client, "set_expression_event"):
            try:
                ev_name = f"agent.event.{event_type}" if event_type else "agent.thinking"
                autonomy_client.set_expression_event(ev_name, {"trace_id": trace_id})
            except Exception:
                pass

        session_language = self._normalize_session_language(language)
        progress_token = self.progress_manager.new_request(language=session_language)
        self._active_progress_token = progress_token
        request_id = uuid.uuid4().hex
        self._active_laya_request_id = request_id
        callback = self._build_progress_callback(progress_token, progress_cb)
        self.tool_registry.status_hook = callback

        try:
            is_short_fast = self._should_fast_path(prompt, native_tools=False)
            use_fast_path = bool(native_tools) or is_short_fast
            self._record_laya_latency(trace_id)

            ack_suppressed = bool(event_type) or self._is_ack_suppressed()
            custom_ack = ""
            if not ack_suppressed:
                laya_eng = getattr(self, "laya_engine", None)
                if laya_eng and getattr(laya_eng, "enabled", True):
                    try:
                        if not use_fast_path:
                            custom_ack = laya_eng.get_instant_filler(language=session_language)
                        laya_dec = self._resolve_turn_laya_decision(prompt, laya_eng)
                        if laya_dec is not None:
                            self._bind_laya_action_request(laya_dec, request_id)
                        if laya_dec and hasattr(self.world_state, "update_laya_state"):
                            self.world_state.update_laya_state(laya_dec)
                        if laya_dec and laya_dec.affective_event in {
                            "user_praise", "user_rude", "joy", "anger", "disgust", "fear", "curiosity", "sadness",
                        }:
                            reaction = laya_eng.get_affective_reaction(
                                laya_dec.affective_event,
                                urgency=float(getattr(laya_dec, "urgency_score", 0.0) or 0.0),
                            )
                            if autonomy_client and hasattr(autonomy_client, "set_expression_event"):
                                autonomy_client.set_expression_event("agent.affect", reaction)
                    except Exception:
                        pass

            stream_state = {"spoken": 0}
            on_sentence = self._make_sentence_callback(session_language, trace_id, stream_state)
            executed_actions: List[Dict[str, Any]] = []

            short_emotion_reply = self._try_short_circuit_emotion_command(
                prompt, session_language, event_type, executed_actions, on_sentence
            )
            if short_emotion_reply is not None:
                dialogue_entry = f"User: {prompt} | Bot: {short_emotion_reply}"
                self._finalize_turn_memory(prompt, short_emotion_reply, dialogue_entry)
                latency_trace.mark(
                    trace_id,
                    "agent.done",
                    {"steps": 1, "speech_handled": stream_state["spoken"] > 0, "short_circuit": "emotion_command"},
                )
                if self.speech_arbiter._speak_fn is None:
                    latency_trace.finish(trace_id, "done")
                return {
                    "text": short_emotion_reply,
                    "thoughts": "System 1 handled emotion command directly without LLM route.",
                    "actions": executed_actions,
                    "plan": [],
                    "model": "system1",
                    "route": [],
                    "subagents": [],
                    "speech_handled": stream_state["spoken"] > 0,
                    "trace_id": trace_id,
                    "latency": latency_trace.get(trace_id),
                }

            provider_error = self._check_provider_availability()
            if provider_error:
                latency_trace.finish(trace_id, str(provider_error.get("error") or "provider_unavailable"))
                out = {**provider_error, "trace_id": trace_id}
                if event_type:
                    out["text"] = ""
                return out

            self.progress_manager.emit_ack(
                progress_token,
                custom_text=custom_ack,
                speak=bool(not ack_suppressed and not use_fast_path),
            )
            survival_override, world_context, active_model = self._prepare_turn_context(
                prompt, session_language, trace_id
            )

            final_text = ""
            total_steps = 0
            subagent_reports: List[Dict[str, Any]] = []

            use_tri_layer = bool(getattr(self, "tri_layer_enabled", False)) and not bool(native_tools) and not is_short_fast
            if use_tri_layer:
                final_text, total_steps, subagent_reports = self._run_tri_layer(
                    prompt,
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
                try:
                    messages = self._native_loop_messages(
                        session_language,
                        world_context=world_context,
                        survival_override=survival_override,
                    )
                except TypeError:
                    messages = self._native_loop_messages(session_language)
                final_text, total_steps = self._run_native_history_loop(
                    active_model,
                    messages,
                    actions_out=executed_actions,
                    num_predict=getattr(self, "fast_path_num_predict", None) if is_short_fast else None,
                    on_sentence=on_sentence,
                    max_steps=(
                        getattr(self, "fast_path_max_steps", 2)
                        if is_short_fast
                        else getattr(self, "max_steps", 4)
                    ),
                    trace_id=trace_id,
                )

            if final_text:
                try:
                    from modules.ai_provider.services.tags import strip_speech_control_artifacts

                    final_text = strip_speech_control_artifacts(final_text)
                except Exception:
                    pass

            dialogue_entry = (
                f"Event({event_type}): {prompt} | Bot: {final_text}"
                if event_type
                else f"User: {prompt} | Bot: {final_text}"
            )
            self._finalize_turn_memory(prompt, final_text, dialogue_entry)

            latency_trace.mark(
                trace_id,
                "agent.done",
                {"steps": total_steps, "speech_handled": stream_state["spoken"] > 0},
            )
            if self.speech_arbiter._speak_fn is None:
                latency_trace.finish(trace_id, "done")
            thoughts = (
                f"Agent reacted to {event_type} in {total_steps} internal steps."
                if event_type
                else f"Agent executed {total_steps} internal steps."
            )
            return {
                "text": final_text,
                "thoughts": thoughts,
                "actions": executed_actions,
                "plan": [],
                "model": active_model,
                "route": self.last_routed_subagents,
                "subagents": subagent_reports,
                "speech_handled": stream_state["spoken"] > 0,
                "trace_id": trace_id,
                "latency": latency_trace.get(trace_id),
            }
        except Exception as exc:
            is_transport = getattr(self, "_is_provider_transport_error", None)
            if callable(is_transport) and is_transport(exc):
                if hasattr(self, "_mark_ollama_unavailable"):
                    self._mark_ollama_unavailable(exc)
                logger.warning(
                    "Agent turn skipped (%s unavailable): %s",
                    getattr(self, "llm_provider", "ollama"),
                    exc,
                )
                latency_trace.finish(trace_id, "ollama_unavailable", {"detail": repr(exc)})
                return self._provider_unavailable_payload(
                    session_language=session_language,
                    event_type=event_type,
                    reason=str(exc),
                    trace_id=trace_id,
                )
            latency_trace.finish(trace_id, "failed", {"detail": repr(exc)})
            raise
        finally:
            self.progress_manager.emit_final(progress_token)
            self.tool_registry.status_hook = previous_hook
            self._active_progress_token = ""
            self._active_laya_request_id = ""
            self._exit_turn()

    def step(
        self,
        user_prompt: str = "",
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        native_tools: bool = False,
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if speaker is None and isinstance(progress_cb, str):
            speaker = progress_cb
            progress_cb = None
        return self._run_turn_core(
            user_prompt,
            bypass_cooldown=False,
            language=language,
            speaker=speaker,
            native_tools=native_tools,
            trace_id=trace_id,
            progress_cb=progress_cb,
            event_type=None,
        )

    def step_event(
        self,
        event_type: str,
        event_prompt: str,
        language: Optional[str] = None,
        speaker: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Event-driven step that bypasses cooldown but not active-turn safety."""
        return self._run_turn_core(
            event_prompt,
            bypass_cooldown=True,
            language=language,
            speaker=speaker,
            native_tools=False,
            trace_id=trace_id,
            progress_cb=None,
            event_type=event_type,
        )

