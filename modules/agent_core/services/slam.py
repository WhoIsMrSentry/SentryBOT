import json
import os
from typing import List, Dict, Any
import logging

logger = logging.getLogger("agent.slam")

class TopologicalMap:
    """
    A Graph-based spatial memory mapping rooms/locations as Nodes.
    Agent uses this to navigate ('go to bedroom', 'where am i').
    """
    def __init__(self, map_file: str = None):
        if map_file is None:
            base = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.abspath(os.path.join(base, "..", "..", ".."))
            map_file = os.path.join(project_root, "data", "map.json")
        self.map_file = map_file
        # Default nodes if map is empty
        self.nodes = {
            "base_station": {"neighbors": ["living_room"], "description": "The charging dock."},
            "living_room": {"neighbors": ["base_station", "kitchen", "hallway"], "description": "Center of the house."},
            "kitchen": {"neighbors": ["living_room"], "description": "Food and water."},
            "hallway": {"neighbors": ["living_room", "bedroom"], "description": "Connecting corridor."},
            "bedroom": {"neighbors": ["hallway"], "description": "Owner's resting area."}
        }
        self.current_location = "base_station"
        self._load_map()

    def _load_map(self):
        try:
            with open(self.map_file, "r") as f:
                saved = json.load(f)
                self.nodes = saved.get("nodes", self.nodes)
                self.current_location = saved.get("current_location", self.current_location)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No saved map found. Using default topomap.")

    def save_map(self):
        import os
        os.makedirs(os.path.dirname(self.map_file), exist_ok=True)
        with open(self.map_file, "w") as f:
            json.dump({"nodes": self.nodes, "current_location": self.current_location}, f, indent=2)

    def get_location(self) -> str:
        return self.current_location

    def update_location(self, new_loc: str) -> bool:
        if new_loc in self.nodes:
            self.current_location = new_loc
            self.save_map()
            return True
        return False

    def pathfind(self, target: str) -> List[str]:
        """BFS pathfinding from current_location to target."""
        if target not in self.nodes:
            return []
            
        queue = [[self.current_location]]
        visited = set([self.current_location])
        
        while queue:
            path = queue.pop(0)
            node = path[-1]
            
            if node == target:
                return path
                
            for neighbor in self.nodes.get(node, {}).get("neighbors", []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)
                    
        return []
