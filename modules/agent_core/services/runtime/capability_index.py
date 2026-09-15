"""Capability ↔ tool indexing for dynamic tool selection."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence


# LLM ToolRegistry names mapped to semantic capabilities.
# Physical execution still goes through autonomy capability/safety gates.
DEFAULT_TOOL_CAPABILITIES: Dict[str, List[str]] = {
    "move_head": ["motion.attend", "hardware.head"],
    "play_sound": ["audio.play", "expression.audio"],
    "set_lights": ["expression.lights"],
    "oled_face": ["expression.face"],
    "set_emotion": ["expression.emotion"],
    "express_emotion": ["expression.emotion", "expression.event"],
    "interaction_event": ["expression.event"],
    "search_memory": ["memory.episodic.search", "knowledge.recall"],
    "search_social_memory": ["memory.social.search", "knowledge.recall"],
    "get_vision": ["vision.cheap", "perception.vision"],
    "get_visual_context": ["vision.cheap", "perception.vision"],
    "describe_scene": ["vision.semantic", "perception.scene"],
    "ask_vlm_about_scene": ["vision.semantic", "perception.vlm"],
    "focus_person": ["perception.track_person", "vision.focus"],
    "remember_person": ["memory.social.write"],
    "update_person_relationship": ["memory.social.write"],
    "get_sensor_data": ["system.inspect", "sensors.read"],
    "get_location": ["navigation.localize"],
    "pathfind": ["navigation.pathfind"],
    "update_location": ["navigation.map.write"],
    "connect_locations": ["navigation.map.write"],
    "list_locations": ["navigation.map.read"],
    "start_owner_follow": ["perception.follow", "motion.follow"],
    "stop_follow": ["perception.follow"],
    "speak": ["communication.speak", "speech.short_prompt"],
    "queue_action": ["action.queue"],
    "get_action_status": ["action.status"],
    "cancel_action": ["action.cancel"],
    "print_to_lcd": ["expression.lcd"],
    "get_last_rfid": ["sensors.rfid"],
}


class CapabilityIndex:
    """Resolve tools by required capability tags.

    Combines static tool→capability metadata with the robot capability registry
    so selection can prefer enabled/low-risk capabilities.
    """

    def __init__(
        self,
        tool_capabilities: Optional[Dict[str, List[str]]] = None,
        registry: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._tool_caps: Dict[str, List[str]] = {
            name: list(caps)
            for name, caps in (tool_capabilities or DEFAULT_TOOL_CAPABILITIES).items()
        }
        self._registry = registry if isinstance(registry, dict) else {}
        self._registry_caps = self._extract_registry_capabilities(self._registry)

    @staticmethod
    def _extract_registry_capabilities(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        for key in ("capabilities", "registry", "items", "actions"):
            value = registry.get(key)
            if isinstance(value, dict):
                return {
                    str(name): (meta if isinstance(meta, dict) else {})
                    for name, meta in value.items()
                }
        return {}

    @classmethod
    def from_robot_registry(cls, tool_capabilities: Optional[Dict[str, List[str]]] = None) -> "CapabilityIndex":
        registry: Dict[str, Any] = {}
        try:
            from modules.autonomy.services.robot_capability_map import load_registry

            loaded = load_registry()
            if isinstance(loaded, dict):
                registry = loaded
        except Exception:
            registry = {}
        return cls(tool_capabilities=tool_capabilities, registry=registry)

    def capabilities_for_tool(self, tool_name: str) -> List[str]:
        return list(self._tool_caps.get(str(tool_name), []))

    def has_registry_capability(self, capability: str) -> bool:
        return str(capability or "").strip() in self._registry_caps

    def is_capability_enabled(self, capability: str) -> bool:
        """Return False only when registry explicitly disables the capability."""
        key = str(capability or "").strip()
        if not key:
            return False
        meta = self._registry_caps.get(key)
        if meta is None:
            return True
        return bool(meta.get("enabled", True))

    def registry_meta(self, capability: str) -> Dict[str, Any]:
        return dict(self._registry_caps.get(str(capability or "").strip()) or {})

    def tools_for_capability(self, capability: str) -> List[str]:
        wanted = str(capability or "").strip()
        if not wanted:
            return []
        matches = [
            name
            for name, caps in self._tool_caps.items()
            if wanted in caps or any(c.startswith(wanted) for c in caps)
        ]
        return sorted(matches)

    def select_tools(
        self,
        required_capabilities: Sequence[str],
        *,
        available_tools: Optional[Iterable[str]] = None,
        prefer_enabled_registry: bool = True,
    ) -> List[str]:
        available = {str(t) for t in (available_tools or self._tool_caps.keys())}
        selected: List[str] = []
        seen = set()
        for capability in required_capabilities:
            candidates = self.tools_for_capability(capability)
            ranked = self._rank_candidates(capability, candidates, available)
            for tool in ranked:
                if tool in seen:
                    continue
                if prefer_enabled_registry and capability in self._registry_caps:
                    meta = self._registry_caps[capability]
                    if meta.get("enabled") is False:
                        continue
                selected.append(tool)
                seen.add(tool)
                break
        return selected

    def _rank_candidates(
        self,
        capability: str,
        candidates: Sequence[str],
        available: set,
    ) -> List[str]:
        usable = [c for c in candidates if c in available]
        if not usable:
            return []
        risk = "unknown"
        meta = self._registry_caps.get(capability) or {}
        if isinstance(meta, dict):
            risk = str(meta.get("risk") or "unknown")
        risk_order = {"none": 0, "low": 1, "semantic": 1, "medium": 2, "high": 3, "critical": 4}
        # Prefer lower-risk capabilities; tool order is stable alphabetical as tie-break
        return sorted(usable, key=lambda t: (risk_order.get(risk, 9), t))

    def capability_gap(
        self,
        required_capabilities: Sequence[str],
        *,
        available_tools: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, str]]:
        gaps: List[Dict[str, str]] = []
        for capability in required_capabilities:
            tools = self.select_tools([capability], available_tools=available_tools)
            if tools:
                continue
            reg = self._registry_caps.get(capability) or {}
            reason = "no_tool_implements_capability"
            if reg.get("enabled") is False:
                reason = "capability_disabled_in_registry"
            elif capability in self._registry_caps and not self.tools_for_capability(capability):
                reason = "registry_capability_without_llm_tool"
            gaps.append(
                {
                    "missing_capability": str(capability),
                    "reason": reason,
                    "suggested_integration": str(reg.get("handler") or ""),
                }
            )
        return gaps

    def describe(self) -> Dict[str, Any]:
        return {
            "tool_count": len(self._tool_caps),
            "registry_capability_count": len(self._registry_caps),
            "tools": sorted(self._tool_caps.keys()),
            "registry_capabilities": sorted(self._registry_caps.keys()),
        }
