"""Visual context model and cache for SentryBOT VLM Bridge.

Standardises the scene understanding data shared across all modules.
The ``VisualContextCache`` holds the latest analysed context so that
Agent Core tools and Autonomy can query it instantly without waiting
for a new VLM round-trip.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vlm_bridge.visual_context")


# ── Data models ───────────────────────────────────────────────────────

@dataclass
class PersonContext:
    """Represents a single person detected in the current frame."""

    track_id: str = ""
    person_id: str = ""
    name: str = "Unknown"
    recognition_level: int = 0  # 0-5
    relationship: str = "unknown"  # owner|family|friend|known|stranger|unknown
    confidence: float = 0.0
    bbox: List[int] = field(default_factory=lambda: [0, 0, 0, 0])  # x1,y1,x2,y2
    distance_m: Optional[float] = None
    gaze_priority: float = 0.0
    last_seen: str = ""
    is_follow_target: bool = False
    appearance_notes: str = ""
    emotion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VisionFrameContext:
    """Complete visual understanding of a single moment."""

    timestamp: str = ""
    scene_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    summary: str = ""
    objects: List[Dict[str, Any]] = field(default_factory=list)
    people: List[PersonContext] = field(default_factory=list)
    hazards: List[Dict[str, Any]] = field(default_factory=list)
    interesting_events: List[Dict[str, Any]] = field(default_factory=list)
    recommended_focus: Dict[str, Any] = field(default_factory=dict)
    importance_score: float = 0.0
    raw_vlm_observation: str = ""
    persona_interpretation: str = ""

    # Metadata
    source: str = "local"  # local | vlm | cached
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["people"] = [p.to_dict() if isinstance(p, PersonContext) else p for p in self.people]
        return d

    @property
    def has_people(self) -> bool:
        return bool(self.people)

    @property
    def has_hazards(self) -> bool:
        return bool(self.hazards)

    @property
    def has_owner(self) -> bool:
        return any(p.recognition_level >= 5 for p in self.people if isinstance(p, PersonContext))

    def get_owner(self) -> Optional[PersonContext]:
        for p in self.people:
            if isinstance(p, PersonContext) and p.recognition_level >= 5:
                return p
        return None

    def get_highest_priority_person(self) -> Optional[PersonContext]:
        if not self.people:
            return None
        valid = [p for p in self.people if isinstance(p, PersonContext)]
        if not valid:
            return None
        return max(valid, key=lambda p: (p.recognition_level, p.gaze_priority))


# ── Importance scoring ────────────────────────────────────────────────

_IMPORTANCE_WEIGHTS = {
    "owner_present": 0.4,
    "new_person": 0.3,
    "hazard_detected": 0.8,
    "user_question": 0.6,
    "scene_change": 0.3,
    "known_person": 0.2,
    "idle_curiosity": 0.1,
}

_IMPORTANCE_PENALTIES = {
    "repeated_scene": -0.4,
    "low_confidence": -0.2,
    "follow_mode_active": -0.15,
}


def compute_importance(
    ctx: VisionFrameContext,
    *,
    is_user_question: bool = False,
    is_scene_change: bool = False,
    is_follow_active: bool = False,
    previous_scene_id: str = "",
) -> float:
    """Compute importance score (0.0 – 1.0) for a context snapshot."""
    score = 0.0

    if ctx.has_owner:
        score += _IMPORTANCE_WEIGHTS["owner_present"]
    if ctx.has_hazards:
        score += _IMPORTANCE_WEIGHTS["hazard_detected"]
    if is_user_question:
        score += _IMPORTANCE_WEIGHTS["user_question"]
    if is_scene_change:
        score += _IMPORTANCE_WEIGHTS["scene_change"]

    for p in ctx.people:
        if isinstance(p, PersonContext):
            if p.recognition_level == 0 and p.name == "Unknown":
                score += _IMPORTANCE_WEIGHTS["new_person"]
            elif p.recognition_level >= 2:
                score += _IMPORTANCE_WEIGHTS["known_person"]

    if not ctx.has_people and not ctx.has_hazards and not is_user_question:
        score += _IMPORTANCE_WEIGHTS["idle_curiosity"]

    # Penalties
    if previous_scene_id and ctx.scene_id == previous_scene_id:
        score += _IMPORTANCE_PENALTIES["repeated_scene"]
    if is_follow_active:
        score += _IMPORTANCE_PENALTIES["follow_mode_active"]

    avg_conf = 0.0
    valid_people = [p for p in ctx.people if isinstance(p, PersonContext)]
    if valid_people:
        avg_conf = sum(p.confidence for p in valid_people) / len(valid_people)
        if avg_conf < 0.3:
            score += _IMPORTANCE_PENALTIES["low_confidence"]

    return max(0.0, min(1.0, score))


# ── Thread-safe cache ─────────────────────────────────────────────────

class VisualContextCache:
    """Thread-safe cache for the latest visual context.

    Usage::

        cache = VisualContextCache()
        cache.update(new_context)
        latest = cache.get_latest()  # instant return
    """

    def __init__(self, max_history: int = 5) -> None:
        self._lock = threading.Lock()
        self._latest: Optional[VisionFrameContext] = None
        self._history: List[VisionFrameContext] = []
        self._max_history = max(1, int(max_history))
        self._update_count = 0
        self._last_update: float = 0.0

    def update(self, ctx: VisionFrameContext) -> None:
        """Store a new context snapshot."""
        with self._lock:
            if self._latest is not None:
                self._history.append(self._latest)
                if len(self._history) > self._max_history:
                    self._history = self._history[-self._max_history:]
            self._latest = ctx
            self._update_count += 1
            self._last_update = time.time()

    def get_latest(self) -> Optional[VisionFrameContext]:
        """Return the most recent context (or None)."""
        with self._lock:
            return self._latest

    def get_latest_dict(self) -> Dict[str, Any]:
        """Return the most recent context as a JSON-safe dict."""
        with self._lock:
            if self._latest is None:
                return {"available": False, "context": None}
            return {
                "available": True,
                "context": self._latest.to_dict(),
                "age_s": round(time.time() - self._last_update, 2),
                "update_count": self._update_count,
            }

    def get_history(self, limit: int = 3) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._history[-limit:])
        return [c.to_dict() for c in items]

    @property
    def age_s(self) -> float:
        with self._lock:
            if self._last_update <= 0:
                return float("inf")
            return time.time() - self._last_update

    @property
    def previous_scene_id(self) -> str:
        with self._lock:
            if self._history:
                return self._history[-1].scene_id
            return ""

    def clear(self) -> None:
        with self._lock:
            self._latest = None
            self._history.clear()
            self._update_count = 0


__all__ = [
    "PersonContext",
    "VisionFrameContext",
    "VisualContextCache",
    "compute_importance",
]
