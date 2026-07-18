from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

VISION_CONTEXT_TO_AUTONOMY_CONTRACT = True
VISION_CONTEXT_TO_AUTONOMY_ROLE = "status_only_vision_semantics_to_autonomy_signal_adapter"
VISION_CONTEXT_TO_AUTONOMY_STATUS_ONLY_SAFE = True


def _now() -> float:
    return float(time())


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any, limit: int = 12) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [str(value)]
    if isinstance(value, Sequence):
        return list(value[:limit])
    return [value]


def _compact_text(value: Any, limit: int = 180) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _merge_bias(target: Dict[str, float], key: str, value: float) -> None:
    target[key] = round(max(float(target.get(key, 0.0)), float(value)), 3)


def _is_risky(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return text not in {"none", "no", "false", "safe", "low", "normal", "ok"}


@dataclass(frozen=True)
class AutonomyVisionSignal:
    kind: str = "vision_context_to_autonomy_signal"
    timestamp: float = 0.0
    observations: List[str] = field(default_factory=list)
    needs_bias: Dict[str, float] = field(default_factory=dict)
    goal_hints: List[str] = field(default_factory=list)
    safety_flags: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    status_only: bool = True
    activation_started: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "timestamp": self.timestamp,
            "observations": list(self.observations),
            "needs_bias": dict(self.needs_bias),
            "goal_hints": list(self.goal_hints),
            "safety_flags": list(self.safety_flags),
            "confidence": self.confidence,
            "status_only": self.status_only,
            "activation_started": self.activation_started,
        }


@dataclass
class VisionContextToAutonomyAdapter:
    """Pure semantic adapter from vision context into autonomy signals.

    The adapter consumes already-produced camera/VLM context dictionaries. It
    never opens a camera, captures a frame, runs a model, makes network calls,
    or mutates robot state. The output is a semantic proposal for autonomy.
    """

    now_fn: Any = _now

    def translate(self, context: Optional[Mapping[str, Any]], *, now: Optional[float] = None) -> AutonomyVisionSignal:
        data = _as_mapping(context)
        entries = self._entries(data)
        timestamp = float(self.now_fn() if now is None else now)

        observations: List[str] = []
        needs_bias: Dict[str, float] = {}
        goal_hints: List[str] = []
        safety_flags: List[str] = []
        confidences: List[float] = []

        for entry in entries:
            item = _as_mapping(entry)
            kind = str(item.get("kind", "")).strip()

            if kind == "camera_status":
                self._apply_camera_status(item, observations, needs_bias, goal_hints)
            elif kind == "vlm_semantic_context":
                self._apply_vlm_semantics(item, observations, needs_bias, goal_hints, safety_flags, confidences)
            else:
                if item:
                    observations.append("vision_context:unknown_entry")

        confidence = round(sum(confidences) / len(confidences), 3) if confidences else None
        return AutonomyVisionSignal(
            timestamp=timestamp,
            observations=observations,
            needs_bias=needs_bias,
            goal_hints=goal_hints,
            safety_flags=safety_flags,
            confidence=confidence,
            status_only=True,
            activation_started=False,
        )

    def _entries(self, data: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        entries = data.get("entries")
        if isinstance(entries, Sequence) and not isinstance(entries, (str, bytes)):
            return [_as_mapping(item) for item in entries]
        if data:
            return [data]
        return []

    def _apply_camera_status(
        self,
        item: Mapping[str, Any],
        observations: List[str],
        needs_bias: Dict[str, float],
        goal_hints: List[str],
    ) -> None:
        enabled = bool(item.get("enabled", False))
        running = bool(item.get("running", False))
        has_frame = bool(item.get("has_frame", False))

        observations.append(f"camera_status:enabled={enabled},running={running},has_frame={has_frame}")

        if enabled and running and has_frame:
            goal_hints.append("use_visual_context_when_needed")
            _merge_bias(needs_bias, "curiosity", 0.05)
        else:
            goal_hints.append("vision_unavailable_keep_audio_memory_behaviour")
            _merge_bias(needs_bias, "visual_confidence", 0.0)

    def _apply_vlm_semantics(
        self,
        item: Mapping[str, Any],
        observations: List[str],
        needs_bias: Dict[str, float],
        goal_hints: List[str],
        safety_flags: List[str],
        confidences: List[float],
    ) -> None:
        caption = _compact_text(item.get("caption", ""))
        objects = [str(obj) for obj in _as_list(item.get("objects", []))]
        people = [str(person) for person in _as_list(item.get("people", []))]
        scene = _compact_text(item.get("scene", ""))
        risk = _compact_text(item.get("risk", ""))

        if caption:
            observations.append(f"caption:{caption}")
        if objects:
            observations.append("objects:" + ",".join(objects[:8]))
            goal_hints.append("inspect_interesting_object")
            _merge_bias(needs_bias, "curiosity", 0.12)
        if people:
            observations.append("people:" + ",".join(people[:8]))
            goal_hints.append("attend_to_known_person")
            _merge_bias(needs_bias, "social", 0.2)
            _merge_bias(needs_bias, "attention", 0.12)
        if scene:
            observations.append(f"scene:{scene}")

        if _is_risky(risk):
            safety_flags.append(f"vision_risk:{risk}")
            goal_hints.append("prefer_safe_observation")
            _merge_bias(needs_bias, "safety", 0.6)

        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None:
            confidences.append(max(0.0, min(1.0, confidence)))


def build_autonomy_vision_signal(
    context: Optional[Mapping[str, Any]],
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    return VisionContextToAutonomyAdapter().translate(context, now=now).as_dict()
