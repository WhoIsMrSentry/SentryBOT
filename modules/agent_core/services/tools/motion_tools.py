from __future__ import annotations

import logging

logger = logging.getLogger("agent.tools.motion")


class MotionToolsMixin:
    """Motion and navigation tools for ToolRegistry."""

    def move_head(self, pan: int, tilt: int) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        safe_pan = self.safety.clamp_servo(pan)
        safe_tilt = self.safety.clamp_servo(tilt)
        resp = self.client.move_head(safe_pan, safe_tilt, source="agent_core", priority=65)
        return (
            f"Head moved to pan={safe_pan}, tilt={safe_tilt}. Hardware response: {resp}"
        )

    def get_location(self) -> str:
        loc = self.slam.get_location()
        return f"You are currently at: {loc}"

    def pathfind(self, destination: str) -> str:
        path = self.slam.pathfind(destination)
        if not path:
            return f"Cannot find path to {destination}."
        return f"Path to {destination}: {' -> '.join(path)}"

    def update_location(self, location: str) -> str:
        ok = self.slam.update_location(location)
        if not ok:
            return f"Failed to update location: {location}"
        return f"Current location updated to: {self.slam.get_location()}"

    def connect_locations(self, source: str, destination: str) -> str:
        ok = self.slam.connect_nodes(source, destination, bidirectional=True)
        if not ok:
            return f"Failed to connect '{source}' and '{destination}'."
        return f"Connected locations: {source} <-> {destination}"

    def list_locations(self) -> str:
        known = self.slam.known_locations()
        if not known:
            return "No known locations yet."
        return f"Known locations: {', '.join(known)}"
