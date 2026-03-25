import logging
import time
import json
from typing import Dict, Any, Optional

from .world_state import WorldState
from .memory import EpisodicMemory
from .slam import TopologicalMap
from .tools import ToolRegistry
from .validator import LLMResponseValidator
from .safety_filter import ActionSafetyFilter
from .planner import TaskPlanner
from .executor import TaskExecutionEngine, AgentState
from .router import ActionRouter
from .sensor_loop import SensorFeedbackLoop
from .idle_behavior import IdleBehaviorSystem

logger = logging.getLogger("agent.orchestrator")

# If ollama library is available.
try:
    import ollama
except ImportError:
    ollama = None


class AgentOrchestrator:
    """
    The heart of SentryBOT's Embodied AI.
    Runs the ReAct Loop (SENSE -> LLM <-> TOOLS -> ACT).
    Implements Survival Instincts and Crash protection.

    IMPORTANT: This does NOT replace AutonomyBrain. It plugs INTO it.
    AutonomyBrain calls agent.step() when it needs the Agent layer
    (multi-step planning, tool-calling, advanced reasoning).
    """

    def __init__(self, config: dict, autonomy_client=None):
        """
        Args:
            config: The agent.yaml config dict.
            autonomy_client: The existing ServiceClient from AutonomyBrain.
                             When provided, the agent uses this client to talk
                             to Ollama (which already has the correct persona
                             loaded via select_persona). This avoids hardcoded
                             system prompts and respects the active persona
                             (sentry, glados, etc.).
        """
        self.config = config
        self.autonomy_client = autonomy_client

        # LLM settings (used only for direct ollama.chat fallback)
        agent_cfg = config.get("agent", {})
        self.model = agent_cfg.get("model", "llama3.2:3b-q4_K_M")
        self.temperature = agent_cfg.get("temperature", 0.15)
        self.num_ctx = agent_cfg.get("num_ctx", 4096)
        self.cooldown = agent_cfg.get("cooldown_s", 1.0)

        # Subsystems
        self.world_state = WorldState()
        self.memory = EpisodicMemory()
        self.slam = TopologicalMap()

        self.tool_registry = ToolRegistry(self.memory, self.slam, self.world_state)

        self.validator = LLMResponseValidator()
        self.safety_filter = ActionSafetyFilter(config)
        self.planner = TaskPlanner()

        # Router needs real ServiceClient to reach hardware via HTTP
        self.router = ActionRouter(autonomy_client) if autonomy_client else ActionRouter.__new__(ActionRouter)
        self.executor = TaskExecutionEngine(self.router)

        # Background threads — pass ServiceClient for real sensor reads
        self.sensor_loop = SensorFeedbackLoop(self.world_state, client=autonomy_client)
        self.idle_system = IdleBehaviorSystem(self.executor, client=autonomy_client)

        self.last_run = 0.0

    def start(self):
        """Start background subsystems (sensors, idle behaviors)."""
        self.sensor_loop.start()
        self.idle_system.start()
        logger.info("AgentOrchestrator subsystems started.")

    def stop(self):
        self.sensor_loop.stop()
        self.idle_system.stop()
        logger.info("AgentOrchestrator subsystems stopped.")

    # ------------------------------------------------------------------
    # Survival Drives
    # ------------------------------------------------------------------
    def check_survival_drives(self):
        """
        Overrides logic if critical limits are reached.
        The Agent takes initiative without waiting for the user.
        """
        bat = self.world_state.get_state().get("battery_percent", 100)
        if bat < 15:
            logger.warning("SURVIVAL DRIVE ACTIVATED: Low Battery (%s%%)!", bat)
            self.executor.interrupt()
            plan_nodes = self.planner.create_plan_queue([
                "stop_current_task",
                "navigate_to_base_station"
            ])
            self.executor.enqueue_plan(plan_nodes)

    # ------------------------------------------------------------------
    # Main Step (called by AutonomyBrain._react_to_speech or externally)
    # ------------------------------------------------------------------
    def step(self, user_prompt: str = "") -> Optional[Dict[str, Any]]:
        """
        One complete Agent thought cycle. Returns the validated response dict.

        The LLM call uses one of two paths:
          1. autonomy_client.chat() -> Uses existing Ollama service with
             the REAL active persona (sentry/glados modelfile).
          2. Direct ollama.chat() fallback -> Only if no autonomy_client
             is available (standalone testing).
        """
        # --- 0. Rate Limits & Survival ---
        now = time.time()
        if now - self.last_run < self.cooldown:
            return None
        self.last_run = now

        self.check_survival_drives()

        # If executor is busy with a long plan, let it step
        if self.executor.current_task and not user_prompt:
            self.executor.step_queue()
            return None

        if not user_prompt:
            return None  # Idle...

        # --- 1. SENSE (World State Injection) ---
        world_context = self.world_state.inject_world_state("")

        # --- 2. THINK (LLM ReAct Loop) ---
        final_response_json = "{}"

        if self.autonomy_client:
            # ====================================================
            # PATH A: Use real persona via existing ServiceClient
            # The Ollama service already has the correct persona
            # (sentry, glados, etc.) loaded. We augment the query
            # with world_state context.
            # ====================================================
            augmented_query = f"{user_prompt}\n{world_context}"
            try:
                resp = self.autonomy_client.chat(augmented_query)
                if resp and isinstance(resp, dict):
                    raw = resp.get("raw", "")
                    # Try to use raw JSON if available
                    if raw:
                        final_response_json = raw
                    else:
                        # Build a valid response from the parsed fields
                        answer = resp.get("text", resp.get("answer", ""))
                        actions = resp.get("actions", [])
                        final_response_json = json.dumps({
                            "text": answer,
                            "thoughts": "Processed via persona pipeline.",
                            "actions": actions if isinstance(actions, list) else [],
                            "plan": []
                        })
            except Exception as e:
                logger.error(f"Persona-based LLM call failed: {e}")
                final_response_json = json.dumps({
                    "text": "LLM crashed during persona call.",
                    "thoughts": "error",
                    "actions": [{"type": "anim", "attrs": {"name": "blink"}}]
                })
        elif ollama:
            # ====================================================
            # PATH B: Direct ollama.chat (standalone / testing)
            # Uses the Modelfile-based persona (model name = persona)
            # ====================================================
            messages = [
                {"role": "user", "content": f"{user_prompt}\n{world_context}"}
            ]

            loop_count = 0
            while loop_count < 3:
                loop_count += 1
                try:
                    response = ollama.chat(
                        model=self.model,
                        messages=messages,
                        format="json",
                        options={
                            "temperature": self.temperature,
                            "num_ctx": self.num_ctx
                        },
                        tools=self.tool_registry.get_tool_schema()
                    )
                except Exception as e:
                    logger.error(f"Direct LLM crash: {e}")
                    final_response_json = json.dumps({
                        "text": "LLM crashed.",
                        "thoughts": "fail",
                        "actions": [{"type": "anim", "attrs": {"name": "blink"}}]
                    })
                    break

                msg = response.get("message", {})

                # --- TOOL CALL INTERCEPTION ---
                if msg.get("tool_calls"):
                    messages.append(msg)
                    for tool in msg["tool_calls"]:
                        fn_name = tool["function"]["name"]
                        fn_args = tool["function"].get("arguments", {})
                        tool_result_str = self.tool_registry.execute(fn_name, fn_args)
                        messages.append({
                            "role": "tool",
                            "content": tool_result_str,
                            "name": fn_name
                        })
                    continue
                else:
                    final_response_json = msg.get("content", "{}")
                    break
        else:
            logger.error("No LLM backend available (no autonomy_client nor ollama).")
            return None

        # --- 3. VALIDATE ---
        valid_dict = self.validator.validate(final_response_json)

        # --- 4. SAFETY FILTER (immediately after validation!) ---
        safe_actions = self.safety_filter.filter_actions(valid_dict.get("actions", []))

        # --- 5. PLAN & ENQUEUE ---
        plan_list = valid_dict.get("plan", [])
        if plan_list:
            nodes = self.planner.create_plan_queue(plan_list)
            self.executor.enqueue_plan(nodes)

        # --- 6. ACT (Execute + Proprioception Feedback) ---
        for act in safe_actions:
            res = self.router.route(act)
            self.world_state.set_action_feedback(res)

        # --- 7. REMEMBER ---
        self.memory.remember(
            "dialogue",
            f"User: {user_prompt} | Bot: {valid_dict.get('text', '')}"
        )

        return valid_dict
