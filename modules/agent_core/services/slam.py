import json
import os
from typing import List, Dict, Any
import logging
import re

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
        self.aliases: Dict[str, str] = {
            "dock": "base_station",
            "charger": "base_station",
            "living": "living_room",
            "bed": "bedroom",
        }
        self._load_map()

    def _load_map(self):
        try:
            with open(self.map_file, "r") as f:
                saved = json.load(f)
                self.nodes = saved.get("nodes", self.nodes)
                self.current_location = saved.get("current_location", self.current_location)
                self.aliases = saved.get("aliases", self.aliases)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.info("No saved map found. Using default topomap.")

    def save_map(self):
        import os
        os.makedirs(os.path.dirname(self.map_file), exist_ok=True)
        with open(self.map_file, "w") as f:
            json.dump(
                {
                    "nodes": self.nodes,
                    "current_location": self.current_location,
                    "aliases": self.aliases,
                },
                f,
                indent=2,
            )

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9_]+", "_", str(text).strip().lower()).strip("_")

    def known_locations(self) -> List[str]:
        return sorted(self.nodes.keys())

    def resolve_location(self, name: str) -> str | None:
        key = self._slug(name)
        if not key:
            return None
        if key in self.nodes:
            return key
        alias_hit = self.aliases.get(key)
        if alias_hit in self.nodes:
            return alias_hit
        for node in self.nodes:
            if key in node:
                return node
        return None

    def add_node(self, name: str, description: str = "") -> str:
        node = self._slug(name)
        if not node:
            return ""
        if node not in self.nodes:
            self.nodes[node] = {"neighbors": [], "description": description or f"Learned node: {node}"}
        if description:
            self.nodes[node]["description"] = description
        self.save_map()
        return node

    def add_alias(self, alias: str, node: str) -> bool:
        node_key = self.resolve_location(node)
        alias_key = self._slug(alias)
        if not node_key or not alias_key:
            return False
        self.aliases[alias_key] = node_key
        self.save_map()
        return True

    def connect_nodes(self, src: str, dst: str, bidirectional: bool = True) -> bool:
        src_key = self.resolve_location(src) or self.add_node(src)
        dst_key = self.resolve_location(dst) or self.add_node(dst)
        if not src_key or not dst_key:
            return False
        if dst_key not in self.nodes[src_key]["neighbors"]:
            self.nodes[src_key]["neighbors"].append(dst_key)
        if bidirectional and src_key not in self.nodes[dst_key]["neighbors"]:
            self.nodes[dst_key]["neighbors"].append(src_key)
        self.save_map()
        return True

    def observe_transition(self, to_location: str, from_location: str | None = None) -> bool:
        src = self.resolve_location(from_location) if from_location else self.current_location
        dst = self.resolve_location(to_location) or self.add_node(to_location)
        if not src or not dst:
            return False
        self.connect_nodes(src, dst, bidirectional=True)
        self.current_location = dst
        self.save_map()
        return True

    def get_location(self) -> str:
        return self.current_location

    def update_location(self, new_loc: str) -> bool:
        resolved = self.resolve_location(new_loc) or self.add_node(new_loc)
        if resolved in self.nodes:
            self.current_location = resolved
            self.save_map()
            return True
        return False

    def pathfind(self, target: str) -> List[str]:
        """BFS pathfinding from current_location to target."""
        target_node = self.resolve_location(target)
        if target_node not in self.nodes:
            return []
            
        queue = [[self.current_location]]
        visited = set([self.current_location])
        
        while queue:
            path = queue.pop(0)
            node = path[-1]
            
            if node == target_node:
                return path
                
            for neighbor in self.nodes.get(node, {}).get("neighbors", []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)
                    
        return []
