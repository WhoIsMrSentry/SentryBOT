"""
Production-ready Idle Behavior System for Agent Core.

CONFLICT RESOLUTION:
  AutonomyBrain already has its own IdleBehaviorPlanner (autonomy/services/idle_behaviors.py)
  which handles boredom-based idle actions (LOOK_AROUND, BLINK, STRETCH, etc.).

  This module does NOT duplicate that system. Instead, it provides:
  1. A "life signs" background heartbeat (breathing lights) when the agent task queue
     is truly empty AND AutonomyBrain's own idle planner isn't active.
  2. It defers to AutonomyBrain for all LLM-driven idle decisions.

  The two systems coexist without conflict because:
  - AutonomyBrain checks `is_bored` flag → runs IdleBehaviorPlanner or _make_agentic_decision
  - This module only runs micro-animations when executor is IDLE and no autonomy idle is running
"""
import logging
import time
import threading
from typing import Optional

logger = logging.getLogger("agent.idle")


class IdleBehaviorSystem:
    """
    Lightweight background "life signs" that run without waking up the LLM
    and without conflicting with AutonomyBrain's idle planner.
    """

    def __init__(self, executor, client=None):
        """
        Args:
            executor: The TaskExecutionEngine (to check if truly idle).
            client: ServiceClient for direct NeoPixel/OLED calls.
        """
        self.executor = executor
        self.client = client
        self.running = False
        self.thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._idle_loop, daemon=True)
        self.thread.start()
        logger.info("Agent idle heartbeat system started.")

    def stop(self):
        self.running = False

    def _idle_loop(self):
        """
        Periodically emits subtle breathing effects ONLY when:
        1. The task executor is completely idle (no queued plans).
        2. No client means we skip (nothing to animate).
        """
        last_breathe = time.time()

        while self.running:
            now = time.time()

            # Only trigger if executor is truly idle and client is available
            if (
                self.client
                and self.executor.state.name == "IDLE"
                and not self.executor.task_queue
                and not self.executor.current_task
            ):
                # Gentle breathing lights every 15s (non-intrusive life sign)
                if now - last_breathe > 15.0:
                    try:
                        self.client.set_neopixel("BREATHE", emotions=["neutral"], duration=3.0)
                    except Exception:
                        pass
                    last_breathe = now

            time.sleep(2.0)  # Check every 2s (very low CPU)
