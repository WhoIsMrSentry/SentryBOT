import json
import logging
import time
from typing import Dict, Any, List, Optional, Tuple
try:
    import ollama
except ImportError:
    ollama = None

from modules.common.model_roles import DEFAULT_UTILITY_MODEL, resolve_role_model
from modules.common.ollama_compat import call_ollama_chat
from modules.common.ollama_url import default_ollama_base_url, normalize_ollama_url

logger = logging.getLogger("autonomy.planner")


def resolve_planner_llm_settings(config: Dict[str, Any]) -> Tuple[str, str, bool]:
    """Resolve (model, normalized_ollama_host, enabled) from root or nested autonomy config."""
    cfg = config if isinstance(config, dict) else {}
    llm_cfg = cfg.get("llm", {}) if isinstance(cfg.get("llm"), dict) else {}
    agent_cfg = cfg.get("agent", {}) if isinstance(cfg.get("agent"), dict) else {}
    fallback = str(cfg.get("planner_model") or llm_cfg.get("model") or DEFAULT_UTILITY_MODEL)
    model = resolve_role_model(cfg, "planner", fallback=fallback)
    raw_url = agent_cfg.get("ollama_base_url") or llm_cfg.get("ollama_base_url") or default_ollama_base_url()
    ollama_host = normalize_ollama_url(raw_url)
    enabled = bool(cfg.get("llm_planning_enabled", True))
    return model, ollama_host, enabled


def format_needs_summary(needs_snapshot: Dict[str, Any]) -> str:
    """Format companion needs scores consistently for BehaviorPlanner and ReflectionPlanner."""
    scores = needs_snapshot.get("scores", {}) if isinstance(needs_snapshot, dict) else {}
    dom = (needs_snapshot or {}).get("dominant_need", "balance") if isinstance(needs_snapshot, dict) else "balance"
    return (
        f"Robot Current Emotions (0-100):\n"
        f"- Boredom: {float(scores.get('boredom', 0) or 0):.0f}\n"
        f"- Curiosity: {float(scores.get('curiosity', 0) or 0):.0f}\n"
        f"- Social Need: {float(scores.get('social', 0) or 0):.0f}\n"
        f"- Energy: {float(scores.get('energy', 0) or 0):.0f}\n\n"
        f"Dominant Emotion: {dom}"
    )


class BehaviorPlanner:
    def __init__(self, config: dict):
        self.config = config
        self.model, self.ollama_host, self.enabled = resolve_planner_llm_settings(config)
        self.goal_queue: List[Dict[str, Any]] = []
        self._last_plan_time = 0.0
        self.cooldown_s = 30.0 # Don't plan too often if queue is empty
        
        try:
            from modules.cognitive_memory.services.world_memory_rag import WorldMemoryRAG
            self.rag = WorldMemoryRAG(config)
        except Exception:
            self.rag = None
        
    def generate_plan(self, needs_snapshot: Dict[str, Any], vision_context: str, recent_reflections: Optional[List[Dict[str, Any]]] = None, tool_schemas: Optional[List[Dict[str, Any]]] = None, social_context: str = "") -> Optional[List[Dict[str, Any]]]:
        if not self.enabled or ollama is None:
            return None
            
        now = time.time()
        if not self.goal_queue and (now - self._last_plan_time) < self.cooldown_s:
            return None # Wait for cooldown to avoid spamming the LLM
            
        system_prompt = (
            "You are the internal cognitive core of SentryBOT. "
            "Stage 1: Analyze the current emotions, visual context, social state, and memories to form a short internal thought. "
            "Stage 2: Select 2-3 tool calls to execute your plan and fulfill your dominant emotion."
        )
        
        reflections_text = ""
        if recent_reflections:
            lines = []
            for ref in recent_reflections[-3:]:
                summary = ref.get("summary") if isinstance(ref, dict) else str(ref)
                if summary:
                    lines.append(f"- {summary}")
            if lines:
                reflections_text = "Recent memory reflections of past actions:\n" + "\n".join(lines) + "\n"
        social_text = f"Social / Person Context: {social_context}\n" if social_context else ""
        
        rag_text = ""
        if self.rag and hasattr(self.rag, "recent"):
            try:
                recent_res = self.rag.recent(limit=5)
                items = recent_res.get("items", []) if isinstance(recent_res, dict) else []
                if items:
                    rag_text = "Spatial & Object RAG Memory:\n"
                    for item in items:
                        lbl = item.get("name") or item.get("label") or item.get("id") or "object"
                        desc = item.get("summary") or item.get("description") or item.get("kind") or ""
                        rag_text += f"- {lbl}: {desc}\n"
                    rag_text += "\n"
            except Exception:
                pass
        
        user_prompt = (
            f"{format_needs_summary(needs_snapshot)}\n"
            f"Camera Vision Context: {vision_context}\n"
            f"{social_text}"
            f"{rag_text}"
            f"{reflections_text}\n"
            "Plan a sequence of 2-3 actions to satisfy your dominant emotion."
        )
        
        try:
            logger.info("Generating LLM behavior plan with native tools...")
            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "think": False,
                "keep_alive": -1,
                "options": {"temperature": 0.15, "num_predict": 160, "num_ctx": 8192}
            }
            if tool_schemas:
                kwargs["tools"] = tool_schemas
            else:
                # Fallback format if no tools provided
                kwargs["format"] = "json"

            client = ollama.Client(host=self.ollama_host)
            response = call_ollama_chat(client, **kwargs)
            
            self._last_plan_time = time.time()
            message = response.get("message", {})
            
            plan = []
            if "tool_calls" in message and message["tool_calls"]:
                for tc in message["tool_calls"]:
                    func = tc.get("function", {})
                    name = func.get("name")
                    args = func.get("arguments", {})
                    if name:
                        # Convert to our internal action schema format
                        action = dict(args)
                        action["tool"] = name
                        action["native_tool_call"] = True
                        plan.append(action)
            elif not tool_schemas:
                # Fallback json parsing
                content = message.get("content", "[]")
                try:
                    plan = json.loads(content)
                except Exception:
                    plan = []
            
            if not plan:
                logger.error("LLM returned empty plan!")
                # Return a fallback plan that just sets neopixel to eye mode
                return [{"tool": "set_neopixel", "effect": "eye", "native_tool_call": True}]
            
            if isinstance(plan, list) and plan:
                logger.info(f"Generated new goal queue with {len(plan)} actions.")
                self.goal_queue.extend(plan)
                return plan
            return None
        except Exception as e:
            logger.error(f"Failed to generate LLM behavior plan: {e}")
            return None

    def get_next_action(self) -> Optional[Dict[str, Any]]:
        if self.goal_queue:
            return self.goal_queue.pop(0)
        return None
