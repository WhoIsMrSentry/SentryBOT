"""
Production-ready Idle Behavior System for Agent Core.

CONFLICT RESOLUTION:
  AutonomyBrain already has its own IdleBehaviorPlanner (autonomy/services/idle_behaviors.py)
  which handles boredom-based idle actions (LOOK_AROUND, BLINK, STRETCH, etc.).

  This module does NOT duplicate that system. Instead, it provides:
  1. A "life signs" background heartbeat (breathing lights) when the agent
     is truly idle AND AutonomyBrain's own idle planner isn't active.
  2. It defers to AutonomyBrain for all LLM-driven idle decisions.
"""
# --- SentryBOT expression/idle boundary contract ---
EXPRESSION_IDLE_COMPATIBILITY = True
EXPRESSION_IDLE_BOUNDARY_ROLE = 'agent_core_compat_idle_heartbeat'
EXPRESSION_IDLE_RUNTIME_OWNER = 'semantic idle decisions: modules.autonomy.services.idle_behaviors; expression output: modules.expression'
EXPRESSION_IDLE_BOUNDARY_REASON = 'IdleBehaviorSystem is still constructed by AgentOrchestrator and provides only a lightweight life-sign heartbeat while deferring semantic idle decisions to autonomy.'
# --- End SentryBOT expression/idle boundary contract ---

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

    def __init__(self, agent_orchestrator, client=None):
        """
        Args:
            agent_orchestrator: The Agent (to check if busy).
            client: ServiceClient for direct NeoPixel/OLED calls.
        """
        self.agent = agent_orchestrator
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
        last_breathe = time.time()

        while self.running:
            now = time.time()

            # Only trigger if agent is truly idle and client is available
            if (
                self.client
                and not self.agent.is_busy
            ):
                # Gentle breathing lights every 15s (non-intrusive life sign)
                if now - last_breathe > 15.0:
                    try:
                        self.client.set_neopixel("BREATHE", emotions=["neutral"], duration=3.0)
                    except Exception:
                        pass
                    last_breathe = now

            time.sleep(2.0)  # Check every 2s (very low CPU)
