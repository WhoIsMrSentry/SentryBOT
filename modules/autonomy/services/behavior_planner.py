import json
import logging
import time
from typing import Dict, Any, List, Optional
try:
    import ollama
except ImportError:
    ollama = None

logger = logging.getLogger("autonomy.planner")

class BehaviorPlanner:
    def __init__(self, config: dict):
        self.config = config
        # Use the primary LLM model from config if possible, fallback to llama3.2
        llm_cfg = config.get("llm", {})
        agent_cfg = config.get("agent", {})
        self.model = llm_cfg.get("model") or config.get("planner_model") or "llama3.2"
        self.ollama_host = agent_cfg.get("ollama_base_url", "http://127.0.0.1:11434")
        self.enabled = config.get("llm_planning_enabled", True)
        self.goal_queue: List[Dict[str, Any]] = []
        self._last_plan_time = 0.0
        self.cooldown_s = 30.0 # Don't plan too often if queue is empty
        
        try:
            from modules.autonomy.services.world_memory_rag import WorldMemoryRAG
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
        
        scores = needs_snapshot.get('scores', {})
        dom = needs_snapshot.get('dominant_need', 'balance')
        
        reflections_text = ""
        if recent_reflections:
            reflections_text = "Recent memory reflections of past actions:\n"
        social_text = f"Social / Person Context: {social_context}\n" if social_context else ""
        
        rag_text = ""
        if self.rag:
            try:
                items = self.rag.recent_observations(limit=5)
                if items:
                    rag_text = "Spatial & Object RAG Memory:\n"
                    for item in items:
                        lbl = item.get("label") or item.get("id") or "object"
                        desc = item.get("description") or item.get("kind") or ""
                        rag_text += f"- {lbl}: {desc}\n"
                    rag_text += "\n"
            except Exception:
                pass
        
        user_prompt = (
            f"Robot Current Emotions (0-100):\n"
            f"- Boredom: {scores.get('boredom', 0):.0f}\n"
            f"- Curiosity: {scores.get('curiosity', 0):.0f}\n"
            f"- Social Need: {scores.get('social', 0):.0f}\n"
            f"- Energy: {scores.get('energy', 0):.0f}\n\n"
            f"Dominant Emotion: {dom}\n"
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
                ]
            }
            if tool_schemas:
                kwargs["tools"] = tool_schemas
            else:
                # Fallback format if no tools provided
                kwargs["format"] = "json"

            client = ollama.Client(host=self.ollama_host)
            response = client.chat(**kwargs)
            
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
