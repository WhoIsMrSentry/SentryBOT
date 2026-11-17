import json
import logging
from typing import Dict, Any, Optional
try:
    import ollama
except ImportError:
    ollama = None

from modules.common.ollama_compat import call_ollama_chat

from .behavior_planner import format_needs_summary, resolve_planner_llm_settings

logger = logging.getLogger("autonomy.reflection")

class ReflectionPlanner:
    def __init__(self, config: dict):
        self.config = config
        self.model, self.ollama_host, self.enabled = resolve_planner_llm_settings(config)
        
    def reflect(self, plan: Dict[str, Any], execution_result: Dict[str, Any], needs_snapshot: Dict[str, Any], vision_context: str) -> Optional[Dict[str, Any]]:
        if not self.enabled or ollama is None:
            return None
            
        system_prompt = (
            "You are the internal reflection engine of a robot. "
            "You analyze the result of a recently executed action and decide if a memory should be formed. "
            "If the action was significant or didn't go as expected (e.g., trying to find someone but the room is empty), "
            "output a JSON object representing a memory to store. "
            "If the action was trivial and went as expected, output an empty JSON object {}. "
            "Format MUST be strict JSON. Example memory output:\n"
            "{\n"
            "  \"summary\": \"I looked around but the room was empty. Scanning doesn't cure my boredom here.\",\n"
            "  \"tags\": [\"boredom_failure\", \"empty_room\"]\n"
            "}"
        )
        
        # Prepare context
        actions = plan.get('actions', [])
        
        user_prompt = (
            f"{format_needs_summary(needs_snapshot)}\n"
            f"Camera Vision Context: {vision_context}\n\n"
            f"Action Attempted: {json.dumps(actions)}\n"
            f"Action Execution Result: {json.dumps(execution_result.get('reason', 'unknown'))}\n\n"
            "Generate a reflection memory JSON, or {} if trivial."
        )
        
        try:
            logger.info("Generating LLM reflection...")
            client = ollama.Client(host=self.ollama_host)
            response = call_ollama_chat(
                client,
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                format="json",
                think=False,
                keep_alive=-1,
                options={"temperature": 0.1, "num_predict": 180, "num_ctx": 8192}
            )
            
            content = response.get("message", {}).get("content", "{}")
            memory = json.loads(content)
            if isinstance(memory, dict):
                memory["candidate_weight_adjustments"] = memory.get("candidate_weight_adjustments", {}) if isinstance(memory.get("candidate_weight_adjustments"), dict) else {}
                memory["temporary_avoid_tags"] = memory.get("temporary_avoid_tags", []) if isinstance(memory.get("temporary_avoid_tags"), list) else []
                memory["preferred_contexts"] = memory.get("preferred_contexts", {}) if isinstance(memory.get("preferred_contexts"), dict) else {}
            
            if isinstance(memory, dict) and memory.get("summary"):
                logger.info(f"Generated reflection memory: {memory.get('summary')}")
                return {
                    "kind": "reflection",
                    "name": "action_result",
                    "summary": memory.get("summary"),
                    "tags": memory.get("tags", []),
                    "candidate_weight_adjustments": memory.get("candidate_weight_adjustments", {}),
                    "temporary_avoid_tags": memory.get("temporary_avoid_tags", []),
                    "preferred_contexts": memory.get("preferred_contexts", {}),
                    "source": "reflection_planner"
                }
            return None
        except Exception as e:
            logger.error(f"Failed to generate LLM reflection plan: {e}")
            return None
