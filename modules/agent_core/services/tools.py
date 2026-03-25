from typing import Dict, Any, Callable, List
import logging

logger = logging.getLogger("agent.tools")

class ToolRegistry:
    """
    Registers python functions that the LLM Agent can invoke natively 
    prior to making its final JSON decision (ReAct Loop).
    """
    def __init__(self, memory, slam, world_state):
        self.memory = memory
        self.slam = slam
        self.world_state = world_state
        self.tools: Dict[str, Callable] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        self.register("search_memory", self._tool_search_memory)
        self.register("get_location", self._tool_get_location)
        self.register("pathfind", self._tool_pathfind)
        self.register("get_battery", self._tool_get_battery)

    def register(self, name: str, func: Callable):
        self.tools[name] = func
        
    def execute(self, tool_name: str, kwargs: Dict[str, Any]) -> str:
        """Executes the mapped tool and returns string result to feed back to LLM."""
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found."
            
        try:
            logger.info(f"Agent internally executing tool: {tool_name} with {kwargs}")
            result = self.tools[tool_name](**kwargs)
            return str(result)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return f"Error executing tool: {e}"

    # --- Implementations ---

    def _tool_search_memory(self, query: str, limit: int = 3) -> str:
        res = self.memory.search_memory(query, limit)
        if not res:
            return "No matching memories found."
        return str(res)

    def _tool_get_location(self) -> str:
        loc = self.slam.get_location()
        return f"You are currently at: {loc}"

    def _tool_pathfind(self, destination: str) -> str:
        path = self.slam.pathfind(destination)
        if not path:
            return f"Cannot find path to {destination}."
        return f"Path to {destination}: {' -> '.join(path)}"

    def _tool_get_battery(self) -> str:
        bat = self.world_state.get_state().get("battery_percent", "unknown")
        return f"Current battery level is {bat}%"

    def get_tool_schema(self) -> List[Dict[str, Any]]:
        """Returns the JSON schema of available tools for the LLM prompt."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_memory",
                    "description": "Searches your episodic memory for a past event, dialogue, or person.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "What to search for"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pathfind",
                    "description": "Finds a topological path from your current location to a known room.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "destination": {"type": "string", "description": "Target room name"}
                        },
                        "required": ["destination"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_location",
                    "description": "Returns your current location on the topological map.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_battery",
                    "description": "Returns the current battery percentage.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
        ]
