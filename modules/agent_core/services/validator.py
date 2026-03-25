import json
import logging
from typing import Dict, Any

logger = logging.getLogger("agent.validator")

class LLMResponseValidator:
    """
    Validates that the output from the Ollama LLM perfectly matches
    the required SentryBOT Schema:
    {
      "text": "...",
      "thoughts": "...",
      "plan": ["...", "..."], // (Optional)
      "actions": [{"type": "...", "attrs": {...}}]
    }
    """
    def __init__(self):
        # Fallback action if parsing completely fails 
        self.fallback = {
            "text": "System error. Rebooting thought process.",
            "thoughts": "I encountered a parsing error.",
            "actions": [{"type": "anim", "attrs": {"name": "blink"}}],
            "plan": []
        }

    def validate(self, raw_llm_output: str) -> Dict[str, Any]:
        """
        Takes raw string from LLM, parses JSON, and validates keys.
        Returns a clean dictionary or a safe fallback.
        """
        try:
            # 1. Parse JSON
            parsed = json.loads(raw_llm_output)
            
            # 2. Check required keys
            required_keys = ["text", "thoughts", "actions"]
            for key in required_keys:
                if key not in parsed:
                    logger.error(f"Validation failed: Missing required key '{key}'")
                    return self.fallback
                    
            # 3. Type check
            if not isinstance(parsed["text"], str):
                parsed["text"] = str(parsed["text"])
            
            if not isinstance(parsed["thoughts"], str):
                parsed["thoughts"] = str(parsed["thoughts"])
                
            if not isinstance(parsed["actions"], list):
                logger.error("Validation failed: 'actions' must be an array")
                return self.fallback
            
            # 4. Optional 'plan' key
            if "plan" not in parsed:
                parsed["plan"] = []
            elif not isinstance(parsed["plan"], list):
                logger.warning("'plan' must be an array. Converting to empty list.")
                parsed["plan"] = []
                
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Validation failed: Invalid JSON string -> {e}")
            return self.fallback
        except Exception as e:
            logger.error(f"Validation failed: Unexpected error -> {e}")
            return self.fallback
