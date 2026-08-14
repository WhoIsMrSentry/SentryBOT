from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("autonomy.perception_context")


class PerceptionContextMixin:
    """Mixin for perception context fusion, visual/audio observation, and sound interrupts."""

    def get_canonical_perception_context(self, base: object = None) -> dict:
        """Merge current vision/audio state into one status-only autonomy context."""
        from modules.autonomy.services.vision_context_to_autonomy import build_autonomy_vision_signal

        base_context = dict(base) if isinstance(base, dict) else {}
        vision = (
            self.state.get("vision_context_needs", {})
            if isinstance(getattr(self, "state", None), dict)
            else {}
        )
        vision = dict(vision) if isinstance(vision, dict) else {}
        audio = (
            self.state.get("audio_event", {})
            if isinstance(getattr(self, "state", None), dict)
            else {}
        )
        audio = dict(audio) if isinstance(audio, dict) else {}
        signal = build_autonomy_vision_signal(vision, now=time.time())
        confidence_values = []
        for value in (
            base_context.get("confidence"),
            signal.get("confidence"),
            vision.get("confidence"),
            audio.get("confidence"),
        ):
            try:
                confidence_values.append(float(value))
            except (TypeError, ValueError):
                pass
        confidence = min(confidence_values) if confidence_values else 0.0
        timestamp = float(vision.get("timestamp", 0.0) or 0.0)
        now = time.time()
        context = dict(base_context)
        context.update({
            "schema": "sentrybot.perception_context.v1",
            "timestamp": timestamp or now,
            "age_s": max(0.0, now - timestamp) if timestamp else None,
            "confidence": confidence,
            "vision_confidence": signal.get("confidence"),
            "audio_confidence": audio.get("confidence"),
            "owner_present": bool(vision.get("owner_present", base_context.get("owner_present", False))),
            "guest_present": bool(vision.get("guest_present", base_context.get("guest_present", False))),
            "new_object": bool(vision.get("new_object", False)),
            "scene_change": bool(vision.get("scene_change", vision.get("new_object", False))),
            "zone": vision.get("zone", base_context.get("zone")),
            "people": vision.get("people", []),
            "audio_event": audio.get("event", audio.get("type")),
            "vision_signal": signal,
        })
        return context

    def _forward_visual_events_to_agent(self) -> None:
        """Forward key autonomy/vision signals to Agent Core event endpoint and trigger LLM reactions."""
        interval = float(getattr(self, "_vision_cfg", {}).get("forward_interval_s", 8.0) or 8.0)
        now = time.time()
        if now - float(self.state.get("last_agent_vision_forward_poll", 0.0) or 0.0) < max(1.0, interval):
            return
        self.state["last_agent_vision_forward_poll"] = now
        if not hasattr(self.client, "emit_agent_event"):
            return
        try:
            ctx_resp = self.client.get_visual_context()
            if not (isinstance(ctx_resp, dict) and ctx_resp.get("available")):
                return
            ctx = ctx_resp.get("context", {}) if isinstance(ctx_resp.get("context", {}), dict) else {}
            hazards = ctx.get("hazards", []) if isinstance(ctx.get("hazards", []), list) else []
            people = ctx.get("people", []) if isinstance(ctx.get("people", []), list) else []
            if hazards:
                self.client.emit_agent_event("hazard_detected", {"count": len(hazards)})
                self.appraise_event("loud_noise", intensity=min(1.0, len(hazards) / 3.0))
                if getattr(self, "agent", None) and self.config.get("llm", {}).get("enabled", False):
                    try:
                        prompt = (
                            f"EVENT: Visual hazard detected! {len(hazards)} hazard(s) in view. "
                            f"React appropriately - express alarm, move to safety, or investigate. "
                            f"Use your tools (like express_emotion) to act, then confirm briefly."
                        )
                        self.agent.step_event("hazard_detected", prompt)
                    except Exception as exc:
                        logger.debug("Hazard event step_event failed: %s", exc)
                return
            owner_seen = False
            new_people = 0
            for p in people:
                if not isinstance(p, dict):
                    continue
                lvl = int(p.get("recognition_level", 0) or 0)
                rel = str(p.get("relationship", "")).lower()
                if lvl >= 5 or rel == "owner":
                    owner_seen = True
                if lvl <= 1:
                    new_people += 1
            if owner_seen:
                self.client.emit_agent_event("owner_follow_intent", {})
                if getattr(self, "agent", None) and self.config.get("llm", {}).get("enabled", False):
                    try:
                        prompt = (
                            f"EVENT: Your owner just appeared in view! "
                            f"Express joy/excitement. Greet them naturally, move your head toward them, "
                            f"maybe say something warm. Use your tools (like express_emotion) to act, then confirm briefly."
                        )
                        self.agent.step_event("owner_seen", prompt)
                    except Exception as exc:
                        logger.debug("Owner seen event step_event failed: %s", exc)
            elif new_people > 0:
                self.client.emit_agent_event("new_person_seen", {"count": new_people})
                self.appraise_event("new_person", intensity=min(1.0, new_people / 2.0))
                if getattr(self, "agent", None) and self.config.get("llm", {}).get("enabled", False):
                    try:
                        prompt = (
                            f"EVENT: You see {new_people} new person/people you don't recognize. "
                            f"React with curiosity or caution. Turn toward them, maybe say hello or observe silently. "
                            f"Use your tools (like express_emotion) to express your reaction, then confirm in one sentence."
                        )
                        self.agent.step_event("new_person_seen", prompt)
                    except Exception as exc:
                        logger.debug("New person event step_event failed: %s", exc)
            elif self.state.get("vision_context_needs", {}).get("new_object"):
                self.appraise_event("new_object", intensity=0.5)
                self.client.emit_agent_event("new_object_seen", {})
                if getattr(self, "agent", None) and self.config.get("llm", {}).get("enabled", False):
                    try:
                        self._make_agentic_decision(
                            reason="vision",
                            context_note="I see a new object that I haven't seen before. I should investigate it.",
                        )
                    except Exception as exc:
                        logger.debug("New object agentic decision failed: %s", exc)
            elif self.state.get("is_bored"):
                self.client.emit_agent_event("idle_comment_request", {"prompt": "look around and comment naturally"})
                if getattr(self, "agent", None) and self.config.get("llm", {}).get("enabled", False):
                    try:
                        prompt = (
                            f"EVENT: You're bored and nothing's happening. Look around the room and make a "
                            f"spontaneous comment or observation. Pick something interesting to look at, "
                            f"express a brief thought. Use your tools (like express_emotion), then speak naturally."
                        )
                        self.agent.step_event("idle_comment", prompt)
                    except Exception as exc:
                        logger.debug("Idle comment event step_event failed: %s", exc)
        except Exception:
            pass

    def handle_sound_interrupt(self, payload: Optional[dict] = None) -> dict:
        try:
            body = payload if isinstance(payload, dict) else {}
            event_type = str(body.get("event_type") or body.get("reason") or "sound").strip().lower()
            is_sound = bool(
                body.get("sound")
                or body.get("wakeword")
                or body.get("speech")
                or event_type in {"sound", "wakeword", "speech", "voice"}
            )
            if not is_sound:
                return {"ok": True, "available": True, "handled": False, "reason": "not_sound_interrupt"}
            actions = []
            try:
                actions.append({
                    "type": "expression",
                    "result": self.client.set_expression_event("sound.interrupt", {"source": event_type, "payload": body}),
                })
            except Exception as exc:
                actions.append({"type": "expression", "ok": False, "error": str(exc)})
            try:
                actions.append({
                    "type": "liveliness",
                    "result": self.client.set_liveliness(True, mode="alert", amplitude_deg=6, period_ms=1800),
                })
            except Exception as exc:
                actions.append({"type": "liveliness", "ok": False, "error": str(exc)})
            try:
                actions.append({"type": "head", "result": self.client.move_head(90, 86)})
            except Exception as exc:
                actions.append({"type": "head", "ok": False, "error": str(exc)})
            try:
                actions.append({
                    "type": "camera_target",
                    "result": self.client._post(
                        "camera", "/tracking/select", {"label": "person", "strategy": "center"}, timeout_s=1.0
                    ),
                })
            except Exception as exc:
                actions.append({"type": "camera_target", "ok": False, "error": str(exc)})
            try:
                if hasattr(self, "observe_world_memory"):
                    self.observe_world_memory(
                        {
                            "kind": "episode",
                            "name": "sound_interrupt",
                            "summary": "Sound interrupted resting or idle behavior; robot woke and looked for the source.",
                            "confidence": 0.7,
                            "salience": 0.7,
                            "tags": ["sound", "interrupt", "wake"],
                            "details": body,
                        },
                        source="audio_interrupt",
                    )
            except Exception:
                pass
            result = {
                "ok": True,
                "available": True,
                "handled": True,
                "timestamp": time.time(),
                "event_type": event_type,
                "actions": actions,
            }
            self.state["sound_interrupt"] = result
            hist = list(self.state.get("sound_interrupt_history") or [])
            hist.append({"timestamp": result["timestamp"], "event_type": event_type, "handled": True})
            self.state["sound_interrupt_history"] = hist[-20:]
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "handled": False, "error": str(exc)}

    def get_sound_interrupt_snapshot(self) -> dict:
        data = self.state.get("sound_interrupt") if isinstance(self.state.get("sound_interrupt"), dict) else {}
        if not data:
            data = {"ok": True, "available": False, "reason": "never_interrupted"}
        out = dict(data)
        out["history"] = list(self.state.get("sound_interrupt_history") or [])[-10:]
        return out

    def observe_vision_context_for_needs(self, payload: Optional[dict] = None, source: str = "api") -> dict:
        try:
            if not hasattr(self, "vision_context_needs_bridge"):
                return {"ok": False, "available": False, "reason": "vision_context_bridge_missing"}
            result = self.vision_context_needs_bridge.observe(payload or {}, source=source)
            self.state["vision_context_needs"] = result
            history = list(self.state.get("vision_context_history") or [])
            history.append({
                "timestamp": result.get("timestamp"),
                "reason": result.get("reason"),
                "summary": result.get("summary", ""),
                "new_object": result.get("new_object", False),
                "owner_present": result.get("owner_present", False),
                "no_person": result.get("no_person", False),
                "hazards": result.get("hazards", []),
            })
            self.state["vision_context_history"] = history[-20:]
            try:
                if hasattr(self, "observe_context_world_memory"):
                    result["memory_autowrite"] = self.observe_context_world_memory("vision", result)
            except Exception:
                pass
            try:
                self.client.push_interaction_event("vision.context", {
                    "reason": result.get("reason"),
                    "summary": result.get("summary", ""),
                    "new_object": result.get("new_object", False),
                    "owner_present": result.get("owner_present", False),
                    "no_person": result.get("no_person", False),
                })
            except Exception:
                pass
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def observe_audio_event_for_needs(self, payload: Optional[dict] = None, source: str = "api") -> dict:
        try:
            if not hasattr(self, "audio_event_needs_bridge"):
                return {"ok": False, "available": False, "reason": "audio_event_bridge_missing"}
            result = self.audio_event_needs_bridge.observe(payload or {}, source=source)
            self.state["audio_event_needs"] = result
            history = list(self.state.get("audio_event_history") or [])
            history.append({
                "timestamp": result.get("timestamp"),
                "reason": result.get("reason"),
                "event_type": result.get("event_type", ""),
                "wakeword": result.get("wakeword", False),
                "speech": result.get("speech", False),
                "sound": result.get("sound", False),
                "silence": result.get("silence", False),
                "loud": result.get("loud", False),
            })
            self.state["audio_event_history"] = history[-20:]
            try:
                if hasattr(self, "observe_context_world_memory"):
                    result["memory_autowrite"] = self.observe_context_world_memory("audio", result)
            except Exception:
                pass
            try:
                self.client.push_interaction_event("audio.context", {
                    "reason": result.get("reason"),
                    "event_type": result.get("event_type", ""),
                    "wakeword": result.get("wakeword", False),
                    "speech": result.get("speech", False),
                    "sound": result.get("sound", False),
                    "silence": result.get("silence", False),
                    "loud": result.get("loud", False),
                })
            except Exception:
                pass
            try:
                if result.get("sound") or result.get("wakeword") or result.get("speech") or result.get("loud"):
                    result["sound_interrupt"] = self.handle_sound_interrupt(result)
            except Exception:
                pass
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_audio_event_needs_snapshot(self) -> dict:
        try:
            current = self.state.get("audio_event_needs")
            if isinstance(current, dict) and current:
                data = dict(current)
            elif hasattr(self, "audio_event_needs_bridge"):
                data = self.audio_event_needs_bridge.status()
            else:
                data = {"ok": False, "available": False, "reason": "audio_event_bridge_missing"}
            data["history"] = list(self.state.get("audio_event_history") or [])[-10:]
            return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_vision_context_needs_snapshot(self) -> dict:
        try:
            current = self.state.get("vision_context_needs")
            if isinstance(current, dict) and current:
                data = dict(current)
            elif hasattr(self, "vision_context_needs_bridge"):
                data = self.vision_context_needs_bridge.status()
            else:
                data = {"ok": False, "available": False, "reason": "vision_context_bridge_missing"}
            data["history"] = list(self.state.get("vision_context_history") or [])[-10:]
            return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def _current_vision_snapshot(self) -> dict:
        out = {}
        try:
            tracks = self.client._get("camera", "/tracking/tracks", timeout_s=0.8)
            if isinstance(tracks, dict):
                out["tracks"] = tracks.get("tracks") if isinstance(tracks.get("tracks"), list) else tracks.get("items", [])
                out["target"] = tracks.get("target")
        except Exception:
            pass
        try:
            ctx = self.state.get("vision_context_needs")
            if isinstance(ctx, dict):
                out.update({k: v for k, v in ctx.items() if k not in out})
        except Exception:
            pass
        return out
