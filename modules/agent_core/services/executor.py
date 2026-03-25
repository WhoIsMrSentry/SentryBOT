"""
Production-ready Task Execution Engine with State Machine.
Manages the lifecycle of Agent tasks (plan steps) and handles interrupts.

State Machine: IDLE -> PLANNING -> EXECUTING -> INTERRUPTED -> ERROR -> IDLE
"""
from enum import Enum
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("agent.executor")


class AgentState(Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"


# Maps high-level plan objectives to concrete action sequences.
# This is the bridge between the Planner's abstract goals and the Router's hardware calls.
PLAN_ACTION_MAP: Dict[str, List[Dict[str, Any]]] = {
    "navigate_to_door": [
        {"type": "stepper", "attrs": {"id": 0, "mode": "vel", "value": 80}},
        {"type": "stepper", "attrs": {"id": 1, "mode": "vel", "value": 80}},
    ],
    "navigate_to_base_station": [
        {"type": "stepper", "attrs": {"id": 0, "mode": "vel", "value": -60}},
        {"type": "stepper", "attrs": {"id": 1, "mode": "vel", "value": -60}},
    ],
    "scan_environment": [
        {"type": "servo", "attrs": {"pan": 30, "tilt": 90}},
        {"type": "servo", "attrs": {"pan": 150, "tilt": 90}},
        {"type": "servo", "attrs": {"pan": 90, "tilt": 90}},
    ],
    "identify_person": [
        {"type": "oled", "attrs": {"action": "anim", "name": "scan"}},
        {"type": "anim", "attrs": {"name": "vision_focus"}},
    ],
    "report_result": [
        {"type": "speak", "attrs": {"text": "Task complete. Here is my report."}},
    ],
    "stop_current_task": [
        {"type": "stepper", "attrs": {"id": 0, "mode": "vel", "value": 0}},
        {"type": "stepper", "attrs": {"id": 1, "mode": "vel", "value": 0}},
    ],
    "look_around": [
        {"type": "anim", "attrs": {"name": "look_around"}},
    ],
    "alert_owner": [
        {"type": "lights", "attrs": {"mode": "PULSE", "emotions": ["alert"]}},
        {"type": "buzzer", "attrs": {"out": "loud", "freq": 3000, "ms": 200}},
    ],
}


class TaskExecutionEngine:
    """
    Manages task lifecycle with a strict State Machine.
    - Queues multi-step plans from the Planner
    - Manages interruptions from owner commands
    - Routes each plan step through the ActionRouter
    - Never blocks the main loop (no time.sleep)
    """

    def __init__(self, router):
        self.state = AgentState.IDLE
        self.task_queue: List[Dict[str, Any]] = []
        self.current_task: Optional[Dict[str, Any]] = None
        self.router = router

    def enqueue_plan(self, plan_queue: List[Dict[str, Any]]):
        """Add planned steps to the execution queue."""
        if plan_queue:
            self.state = AgentState.PLANNING
            self.task_queue.extend(plan_queue)
            logger.info("Enqueued %d plan steps. Queue size: %d", len(plan_queue), len(self.task_queue))

    def execute_immediate_actions(self, actions: List[Dict[str, Any]]):
        """
        Execute actions that came directly from the LLM response (not from a plan).
        These are instant and don't go through the task queue.
        """
        if not actions:
            return

        prev_state = self.state
        self.state = AgentState.EXECUTING
        try:
            for action in actions:
                feedback = self.router.route(action)
                if "ERROR" in str(feedback):
                    logger.warning("Immediate action error: %s -> %s", action.get("type"), feedback)
        except Exception as e:
            logger.error("Executor failed matching actions to router: %s", e)
            self.state = AgentState.ERROR
            return
        # Restore state (don't override if there are queued tasks)
        if not self.task_queue and not self.current_task:
            self.state = AgentState.IDLE
        else:
            self.state = prev_state

    def step_queue(self) -> Optional[str]:
        """
        Called periodically to advance one multi-step plan task.
        Returns the feedback string from the executed step, or None.
        Does NOT block — executes one step per call.
        """
        if self.state == AgentState.INTERRUPTED:
            return None

        # Nothing to do
        if not self.task_queue and not self.current_task:
            if self.state != AgentState.IDLE:
                self.state = AgentState.IDLE
            return None

        # Pick next task from queue
        if not self.current_task:
            self.current_task = self.task_queue.pop(0)

        self.state = AgentState.EXECUTING
        obj = self.current_task.get("objective", "")
        logger.info("Executing plan step: %s (retry=%d)", obj, self.current_task.get("retries", 0))

        # Resolve objective to concrete actions via the mapping table
        actions = PLAN_ACTION_MAP.get(obj, [])
        if not actions:
            logger.warning("No action mapping for objective '%s'. Skipping.", obj)
            self.current_task["status"] = "skipped"
            self.current_task = None
            return "SKIPPED_NO_MAPPING"

        # Execute all actions for this step
        last_feedback = "SUCCESS"
        try:
            for act in actions:
                feedback = self.router.route(act)
                if "ERROR" in str(feedback):
                    logger.warning("Plan step '%s' action error: %s", obj, feedback)
                    last_feedback = feedback
                    # Retry logic
                    retries = self.current_task.get("retries", 0)
                    if retries < 2:
                        self.current_task["retries"] = retries + 1
                        logger.info("Retrying step '%s' (attempt %d)...", obj, retries + 1)
                        return feedback  # Will retry on next step_queue call
                    else:
                        self.current_task["status"] = "failed"
                        self.state = AgentState.ERROR
                        self.current_task = None
                        return feedback
        except Exception as e:
            logger.error("Plan step execution exception: %s", e)
            self.state = AgentState.ERROR
            self.current_task = None
            return f"ERROR_EXCEPTION_{e}"

        # Step completed successfully
        self.current_task["status"] = "completed"
        logger.info("Plan step '%s' completed.", obj)
        self.current_task = None

        # Check if entire plan is done
        if not self.task_queue:
            self.state = AgentState.IDLE
            logger.info("All plan steps completed. Returning to IDLE.")

        return last_feedback

    def interrupt(self):
        """Owner command interrupted the current plan. Emergency stop."""
        self.state = AgentState.INTERRUPTED
        self.task_queue.clear()
        self.current_task = None
        try:
            self.router.route({"type": "stepper", "attrs": {"id": 0, "mode": "vel", "value": 0}})
            self.router.route({"type": "stepper", "attrs": {"id": 1, "mode": "vel", "value": 0}})
        except Exception:
            pass
        logger.warning("Agent Execution INTERRUPTED. All queues cleared, motors stopped.")

    def resume(self):
        """Resume from interrupted state (allows new plans to be enqueued)."""
        if self.state == AgentState.INTERRUPTED:
            self.state = AgentState.IDLE
            logger.info("Agent execution RESUMED.")
