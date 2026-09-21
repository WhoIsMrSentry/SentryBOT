# --- SentryBOT memory/world boundary contract ---
MEMORY_WORLD_COMPATIBILITY = True
MEMORY_WORLD_BOUNDARY_ROLE = 'agent_core_compat_world_state'
MEMORY_WORLD_RUNTIME_OWNER = 'modules.cognitive_memory.services.world_memory'
MEMORY_WORLD_BOUNDARY_REASON = 'WorldState is still used by AgentOrchestrator, ToolRegistry, SensorFeedbackLoop, and /world_state endpoint; keep as compatibility state surface.'
# --- End SentryBOT memory/world boundary contract ---

import json
from datetime import datetime
from typing import Dict, Any

class WorldState:
    """
    Maintains the real-time context of the robot.
    Added Chrono-awareness, Location mapping, and Action Outcome handling.
    """
    def __init__(self):
        import threading as _threading

        self._state_lock = _threading.RLock()
        self.state: Dict[str, Any] = {
            "distance_front_cm": -1,
            "battery_percent": 100,
            "person_detected": False,
            "last_rfid": None,
            "is_moving": False,
            "location": "unknown",
            "last_action_feedback": "None" # Success or motor stall errors
        }
        # Continuous environment perception (fed from the VLM scene cache).
        self.environment: Dict[str, Any] = {
            "scene_summary": "",
            "objects": [],
            "hazards": [],
            "people_present": [],
            "importance": 0.0,
            "updated_at": "",
        }
        
    def update_state(self, updates: Dict[str, Any]):
        with self._state_lock:
            self.state.update(updates)

    def update_scene(self, context: Dict[str, Any]) -> None:
        """Ingest a VLM visual-context snapshot into the environment model.

        Accepts either the raw context dict or the cache envelope
        ``{"available": ..., "context": {...}}`` returned by the vlm_bridge API.
        """
        if not isinstance(context, dict):
            return
        ctx = context.get("context") if "context" in context and isinstance(context.get("context"), dict) else context
        if not isinstance(ctx, dict) or not ctx:
            return
        people = []
        for p in ctx.get("people", []) or []:
            if isinstance(p, dict):
                name = str(p.get("name", "") or "").strip()
                if name and name.lower() != "unknown":
                    people.append(name)
        environment = {
            "scene_summary": str(ctx.get("summary", "") or ""),
            "objects": [str(o.get("label", o)) if isinstance(o, dict) else str(o) for o in (ctx.get("objects", []) or [])][:8],
            "hazards": [str(h.get("label", h)) if isinstance(h, dict) else str(h) for h in (ctx.get("hazards", []) or [])][:5],
            "people_present": people[:6],
            "importance": float(ctx.get("importance_score", 0.0) or 0.0),
            "updated_at": str(ctx.get("timestamp", "") or datetime.now().isoformat()),
        }
        with self._state_lock:
            self.environment = environment

    def get_laya_scene_summary(self, max_chars: int = 100) -> str:
        """Return a bounded, thread-safe visual summary for Laya inference."""
        with self._state_lock:
            environment = dict(self.environment)
            hazards = list(environment.get("hazards", []))[:2]
            objects = list(environment.get("objects", []))[:5]
            people = list(environment.get("people_present", []))[:3]
        parts = []
        summary = str(environment.get("scene_summary", "") or "").strip()
        if summary:
            parts.append(summary)
        if people:
            parts.append(f"bilinen kişiler: {', '.join(str(person) for person in people)}")
        if objects:
            parts.append(f"nesneler: {', '.join(str(item) for item in objects)}")
        if hazards:
            parts.append(f"tehlikeler: {', '.join(str(item) for item in hazards)}")
        return "; ".join(parts)[:max(1, int(max_chars))]

    def update_laya_state(self, decision: Any) -> None:
        """Publish a compact snapshot of the latest Laya decision."""
        if decision is None:
            return
        try:
            snapshot = {
                "laya_last_target": str(getattr(decision, "target_module", "") or ""),
                "laya_last_urgency": float(getattr(decision, "urgency_score", 0.0) or 0.0),
                "laya_last_affect": str(getattr(decision, "affective_event", "neutral") or "neutral"),
                "laya_last_direct": bool(getattr(decision, "is_direct_command", False)),
                "laya_last_ms": float(getattr(decision, "inference_ms", 0.0) or 0.0),
            }
        except (TypeError, ValueError):
            return
        self.update_state(snapshot)
        
    def set_action_feedback(self, feedback: str):
        with self._state_lock:
            self.state["last_action_feedback"] = feedback

    def get_state(self) -> Dict[str, Any]:
        # Copy under lock: readers never see partial updates (R8).
        with self._state_lock:
            return dict(self.state)
        
    def inject_world_state(self, base_prompt: str) -> str:
        """
        Injects real-time state plus Chrono-awareness into the LLM context.
        """
        now = datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        hour = now.hour
        
        # Chrono-awareness heuristic
        time_of_day = "Night"
        if 6 <= hour < 12:
            time_of_day = "Morning"
        elif 12 <= hour < 18:
            time_of_day = "Afternoon"
        elif 18 <= hour < 22:
            time_of_day = "Evening"
            
        chrono = {
            "datetime": time_str,
            "time_of_day": time_of_day
        }
        
        context = {
            "chrono": chrono,
            "sensors": self.state
        }
        # Only surface the environment block when we actually have a scene, so
        # the prompt stays lean when vision is idle.
        if self.environment.get("scene_summary") or self.environment.get("people_present"):
            context["environment"] = self.environment

        state_str = json.dumps(context, indent=2)
        injected = f"{base_prompt}\n\n[SYSTEM WORLD STATE]\n{state_str}\n"
        return injected
