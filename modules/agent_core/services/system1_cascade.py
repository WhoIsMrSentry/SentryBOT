from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional, Sequence, Tuple

from modules.agent_core.services.system1_rules import classify as rules_classify

logger = logging.getLogger("agent.system1_cascade")


class System1CascadeEngine:
    """Tiered System 1 engine: rules (<1ms) -> embedding (~50ms) -> Laya neural.

    Exposes the exact LayaEngine public contract, so any consumer can receive
    this instance transparently. Falls through to the neural backend only when
    the cheaper tiers do not produce a confident decision.
    """

    _instance: Optional["System1CascadeEngine"] = None
    _lock = threading.Lock()

    MODULE_TOOL_MAP: Dict[str, str] = {
        "neopixel": "set_lights",
        "arduino_serial": "move_head",
        "emergency_stop": "stop_follow",
        "speak": "speak",
        "camera": "get_vision",
    }

    def __init__(self, laya_engine: Any, s1_cfg: Dict[str, Any]) -> None:
        self._laya = laya_engine
        self.enabled = bool(s1_cfg.get("enabled", True))
        rules_cfg = s1_cfg.get("rules", {}) if isinstance(s1_cfg.get("rules"), dict) else {}
        self.rules_enabled = bool(rules_cfg.get("enabled", True))
        embed_cfg = s1_cfg.get("embed", {}) if isinstance(s1_cfg.get("embed"), dict) else {}
        self._embed = None
        self._embed_enabled = bool(embed_cfg.get("enabled", True))
        self._embed_cfg = embed_cfg
        self._tier_counts: Dict[str, int] = {"rules": 0, "embed": 0, "laya": 0, "none": 0}
        self._last_backend = "none"

    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> "System1CascadeEngine":
        with cls._lock:
            if cls._instance is None:

                tri = (config or {}).get("tri_layer", {})
                if not isinstance(tri, dict):
                    tri = {}
                s1_cfg = tri.get("system1", {})
                if not isinstance(s1_cfg, dict):
                    s1_cfg = {}
                laya = System1CascadeEngine._fresh_laya(config)
                cls._instance = cls(laya, s1_cfg)
            return cls._instance

    @staticmethod
    def _fresh_laya(config: Optional[Dict[str, Any]]) -> Any:
        from modules.agent_core.services import laya_engine as laya_mod

        return laya_mod.LayaEngine.get_instance(config, raw=True)

    @property
    def confidence_threshold(self) -> float:
        return self._laya.confidence_threshold

    @property
    def is_available(self) -> bool:
        return True

    @property
    def fast_path_enabled(self) -> bool:
        return self._laya.fast_path_enabled

    @property
    def laya(self) -> Any:
        return self._laya

    @property
    def embed(self) -> Any:
        if self._embed is None and self._embed_enabled:
            from modules.agent_core.services.system1_embed import System1EmbedEngine

            self._embed = System1EmbedEngine.get_instance(self._embed_cfg)
        return self._embed

    def decide(self, text: str) -> Optional[Any]:
        cleaned = str(text or "").strip()
        if not cleaned:
            return None

        if self.rules_enabled:
            decision = rules_classify(cleaned, action_proposal_cfg=self._laya.action_proposal_cfg)
            if decision is not None:
                if decision.suggested_tool is None:
                    decision.suggested_tool = self.MODULE_TOOL_MAP.get(decision.target_module)
                self._laya._record_telemetry(cleaned, decision)
                self._record("rules")
                return decision

        embed_engine = self.embed if self._embed_enabled else None
        if embed_engine is not None and embed_engine.is_available:
            decision = embed_engine.decide(cleaned)
            if decision is not None:
                if decision.suggested_tool is None:
                    decision.suggested_tool = self.MODULE_TOOL_MAP.get(decision.target_module)
                self._laya._record_telemetry(cleaned, decision)
                self._record("embed")
                return decision

        if getattr(self._laya, "_agent", None) is not None:
            decision = self._laya.decide(cleaned)
            if decision is not None:
                self._record("laya")
                return decision

        self._record("none")
        return None

    def decide_with_context(
        self,
        text: str,
        world_state: Optional[Dict[str, Any]] = None,
        visual_context: Optional[str] = None,
    ) -> Optional[Any]:
        enriched = str(text or "").strip()
        if not enriched:
            return None
        if visual_context:
            scene_hint = str(visual_context)[:100]
            enriched = f"{enriched} [Sahne: {scene_hint}]"

        decision = self.decide(enriched)
        if decision is None:
            return None

        if not isinstance(world_state, dict):
            return decision

        battery = world_state.get("battery_percent", 100)
        try:
            bat_val = float(battery)
        except (TypeError, ValueError):
            bat_val = 100.0
        if bat_val < 15 and decision.urgency_score < self._laya.high_urgency_threshold:
            decision.urgency_score = self._laya.high_urgency_threshold

        follow_active = bool(world_state.get("follow_active", False))
        if follow_active and decision.target_module == "camera":
            decision.module_confidence = min(1.0, decision.module_confidence + 0.15)

        return decision

    def should_fast_path(
        self,
        user_prompt: str,
        world_state: Optional[Dict[str, Any]] = None,
        visual_context: Optional[str] = None,
    ) -> Tuple[bool, Optional[Any]]:
        if not self._laya.fast_path_enabled:
            return False, None

        decision = self.decide_with_context(
            user_prompt, world_state=world_state, visual_context=visual_context
        )
        if decision is None:
            return False, None

        if decision.is_emergency:
            return True, decision

        if decision.urgency_score >= self._laya.high_urgency_threshold:
            if decision.is_direct_command and decision.direct_confidence >= self._laya.confidence_threshold:
                return True, decision

        if decision.is_direct_command and decision.direct_confidence >= self._laya.confidence_threshold:
            if decision.target_module in {"neopixel", "arduino_serial", "speak", "emergency_stop"}:
                return True, decision

        return False, decision

    def route(self, user_prompt: str, available_modules: Sequence[str]) -> list[str]:
        decision = self.decide(user_prompt)
        if decision is None:
            return []
        if decision.module_confidence < self._laya.confidence_threshold:
            return []
        target = decision.target_module
        if target in available_modules:
            return [target]
        alias_map = {
            "emergency_stop": ["arduino_serial", "autonomy"],
            "camera": ["vlm_bridge", "camera"],
            "speak": ["speak"],
            "neopixel": ["neopixel", "interactions"],
            "arduino_serial": ["arduino_serial", "hardware"],
            "system2_chat": ["autonomy", "agent_core"],
        }
        candidates = alias_map.get(target, [])
        return [c for c in candidates if c in available_modules]

    def is_urgent(self, decision: Optional[Any] = None) -> bool:
        dec = decision or self._last_decision()
        if dec is None:
            return False
        return bool(getattr(dec, "is_emergency", False)) or (
            dec.urgency_score >= self._laya.high_urgency_threshold
            and dec.urgency_confidence >= self._laya.high_urgency_confidence_threshold
        )

    def is_emergency_decision(self, decision: Optional[Any] = None) -> bool:
        dec = decision or self._last_decision()
        if dec is None:
            return False
        return bool(getattr(dec, "is_emergency", False))

    def get_instant_filler(self, language: str = "tr") -> str:
        return self._laya.get_instant_filler(language)

    def get_filler_with_affect(self, language: str = "tr", mood: str = "neutral") -> str:
        return self._laya.get_filler_with_affect(language, mood)

    def get_fast_ack(self, language: str = "tr") -> str:
        return self._laya.get_fast_ack(language)

    def get_affective_reaction(self, affect: str, urgency: float = 0.0) -> Dict[str, Any]:
        return self._laya.get_affective_reaction(affect, urgency)

    def get_mood_deltas(self, decision: Optional[Any] = None) -> Dict[str, float]:
        return self._laya.get_mood_deltas(decision or self._last_decision())

    def _last_decision(self) -> Optional[Any]:
        return self._laya._last_decision

    def _record(self, backend: str) -> None:
        self._last_backend = backend
        self._tier_counts[backend] = self._tier_counts.get(backend, 0) + 1

    def get_telemetry(self) -> Dict[str, Any]:
        laya_stats = self._laya.get_telemetry()
        embed_stats = self.embed.get_telemetry() if self._embed_enabled else {"enabled": False}
        laya_stats["cascade_backend"] = "cascade"
        laya_stats["last_backend"] = self._last_backend
        laya_stats["tier_counts"] = dict(self._tier_counts)
        laya_stats["embed_backend"] = embed_stats
        return laya_stats


__all__ = ["System1CascadeEngine"]
