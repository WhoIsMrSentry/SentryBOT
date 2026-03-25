from typing import List, Dict, Any
import logging

logger = logging.getLogger("agent.planner")

class TaskPlanner:
    """
    Translates high-level string 'plan' entries from the LLM
    into sequential task nodes that the Executor can manage.
    """
    def __init__(self):
        # A dictionary to map plan strings to low-level preset functions
        # For demonstration, we simply wrap them in an objective object.
        pass

    def create_plan_queue(self, plan_strings: List[str]) -> List[Dict[str, Any]]:
        """
        Converts:
        ["navigate_to_door", "scan_environment"]
        Into:
        [
          {"step_id": 0, "objective": "navigate_to_door", "status": "pending"},
          {"step_id": 1, "objective": "scan_environment", "status": "pending"}
        ]
        """
        queue = []
        if not plan_strings:
            return queue
            
        for i, p_str in enumerate(plan_strings):
            queue.append({
                "step_id": i,
                "objective": str(p_str),
                "status": "pending",
                "retries": 0
            })
            
        logger.info(f"Planned {len(queue)} sequential steps.")
        return queue
