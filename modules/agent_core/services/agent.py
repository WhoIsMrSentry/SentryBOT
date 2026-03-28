import logging
import time
from typing import Dict, Any, Optional

from .world_state import WorldState
from .memory import EpisodicMemory
from .slam import TopologicalMap
from .tools import ToolRegistry
from .safety_filter import ActionSafetyFilter
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
    SentryBOT's Embodied AI - Native Tool Calling Edition.
    Runs an autonomous loop up to MAX_STEPS allowing unrestricted
    tool use (e.g. database search -> look around -> move head) in one reasoning pass.
    """

    def __init__(self, config: dict, autonomy_client=None):
        """
        Args:
            config: The agent.yaml config dict.
            autonomy_client: ServiceClient used to trigger real hardware.
        """
        self.config = config
        self.autonomy_client = autonomy_client

        # LLM settings
        agent_cfg = config.get("agent", {})
        self.model = agent_cfg.get("model", "llama3.2:3b-q4_K_M")
        self.temperature = agent_cfg.get("temperature", 0.15)
        self.num_ctx = agent_cfg.get("num_ctx", 4096)
        self.cooldown = agent_cfg.get("cooldown_s", 1.0)
        self.max_steps = agent_cfg.get("max_steps", 10)

        # Subsystems
        self.world_state = WorldState()
        self.memory = EpisodicMemory()
        self.slam = TopologicalMap()
        self.safety_filter = ActionSafetyFilter(config)
        self.tool_registry = ToolRegistry(
            client=self.autonomy_client,
            memory=self.memory,
            slam=self.slam,
            world_state=self.world_state,
            safety_filter=self.safety_filter
        )

        # Background threads
        self.sensor_loop = SensorFeedbackLoop(self.world_state, client=autonomy_client)
        self.idle_system = IdleBehaviorSystem(self, client=autonomy_client)

        self.last_run = 0.0
        self.is_busy = False
        
        # Short-term conversational/reasoning memory across steps
        self.chat_history = []
        self.max_history = agent_cfg.get("max_history", 10)

    def start(self):
        """Start background subsystems."""
        self.sensor_loop.start()
        self.idle_system.start()
        logger.info("AgentOrchestrator subsystems started.")

    def stop(self):
        self.sensor_loop.stop()
        self.idle_system.stop()
        logger.info("AgentOrchestrator subsystems stopped.")

    def check_survival_drives(self):
        """Overrides logic if critical limits are reached."""
        bat = self.world_state.get_state().get("battery_percent", 100)
        if bat < 15:
            logger.warning("SURVIVAL DRIVE: Low Battery (%s%%)!", bat)
            return "[CRITICAL] Battery is severely low. Do not engage in lengthy tasks. Find a charger or warn the user."
        return None

    def _append_history(self, role: str, content: str, tool_calls=None, tool_name=None):
        msg = {"role": role, "content": content}
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_name is not None:
            msg["name"] = tool_name
            
        self.chat_history.append(msg)
        # Keep last N * 2 turns
        limit = self.max_history * 2
        if len(self.chat_history) > limit:
            self.chat_history = self.chat_history[-limit:]

    def _get_active_persona_model(self) -> str:
        """Fetch the current model name from the autonomy/ollama module."""
        # fallback to config if we can't determine it
        return self.config.get("llm", {}).get("model", "qwen3.5:2b")

    def step(self, user_prompt: str = "") -> Optional[Dict[str, Any]]:
        """
        One complete Agent thought cycle.
        Executes a multi-stage tool-calling loop (max N steps).
        """
        now = time.time()
        if now - self.last_run < self.cooldown:
            return None
        self.last_run = now

        if self.is_busy or not user_prompt:
            return None
            
        self.is_busy = True

        try:
            # 1. Collect world & survival context
            survival_override = self.check_survival_drives()
            world_context = self.world_state.inject_world_state("")
            
            full_prompt = f"{user_prompt}\n\n[World State]\n{world_context}"
            if survival_override:
                full_prompt += f"\n\n{survival_override}"
                
            self._append_history("user", full_prompt)

            # 2. Prepare message stack for Ollama
            # System prompt is now inside the Modelfile on the server.
            messages = list(self.chat_history)
            
            tools = self.tool_registry.get_tool_schema()
            active_model = self._get_active_persona_model()
            
            final_text = ""

            if not ollama:
                logger.error("Ollama library not found. Native tool loop requires 'ollama' package.")
                return {"text": "System Error: Missing ollama backend."}

            # 3. Native ReAct Loop
            step_idx = 0
            for step_idx in range(self.max_steps):
                try:
                    response = ollama.chat(
                        model=active_model,
                        messages=messages,
                        tools=tools,
                        options={
                            "temperature": self.temperature,
                            "num_ctx": self.num_ctx
                        }
                    )
                except Exception as e:
                    logger.error(f"LLM tool loop crashed: {e}")
                    final_text = "System fault during cognitive cycle."
                    break

                msg = response.get("message", {})
                messages.append(msg)
                
                # Check if LLM decided to use tools
                if msg.get("tool_calls"):
                    tool_calls = msg["tool_calls"]
                    log_tc = [{"name": t["function"]["name"], "args": t["function"]["arguments"]} for t in tool_calls]
                    logger.info(f"Agent Loop [{step_idx+1}/{self.max_steps}] Using tools: {log_tc}")
                    
                    self._append_history("assistant", msg.get("content", ""), tool_calls=tool_calls)

                    # Execute each tool
                    for tool in tool_calls:
                        fn_name = tool["function"]["name"]
                        fn_args = tool["function"].get("arguments", {})
                        
                        tool_result_str = self.tool_registry.execute(fn_name, fn_args)
                        
                        tool_msg = {
                            "role": "tool",
                            "content": tool_result_str,
                            "name": fn_name
                        }
                        messages.append(tool_msg)
                        self._append_history("tool", tool_result_str, tool_name=fn_name)
                        
                else:
                    # No tool calls -> Loop is complete, this is the final answer
                    final_text = msg.get("content", "")
                    self._append_history("assistant", final_text)
                    logger.info(f"Agent Final Response: {final_text}")
                    break
                    
            if not final_text:
                final_text = "Task completed using internal tools."
                
            # 4. Save to episodic long-term memory
            self.memory.remember("dialogue", f"User: {user_prompt} | Bot: {final_text}")
            
            # 5. Return dict matching AutonomyBrain expectations (but empty plan/actions)
            return {
                "text": final_text,
                "thoughts": f"Native ReAct Loop executed in {step_idx+1} steps.",
                "actions": [], 
                "plan": [] 
            }
            
        finally:
            self.is_busy = False
