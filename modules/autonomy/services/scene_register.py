"""SceneRegister — Peripheral Vision L1 continuous scene tracking.

Maintains a sliding 2-5 second RAM-only summary of the environment:
- 9-grid spatial distribution of people & obstacles
- Motion energy per region (frame-diff / optical flow / bounding box activity)
- Sound Direction of Arrival (DoA) & salience
- High-level single-sentence summary for LLM prompt context
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("autonomy.scene_register")

# 9-grid spatial layout
REGIONS_3X3 = [
    "top_left",    "top_center",    "top_right",
    "mid_left",    "center",        "mid_right",
    "bottom_left", "bottom_center", "bottom_right",
]

REGION_NAMES_TR = {
    "top_left": "sol-üst",
    "top_center": "üst-orta",
    "top_right": "sağ-üst",
    "mid_left": "sol-orta",
    "center": "merkez",
    "mid_right": "sağ-orta",
    "bottom_left": "sol-alt (arka)",
    "bottom_center": "ön-alt",
    "bottom_right": "sağ-alt (arka)",
}


def bbox_to_region(x: float, y: float, w: float, h: float) -> str:
    """Convert normalized bbox (0.0 - 1.0) center coordinates to a 9-grid region name."""
    cx = max(0.0, min(1.0, x + w / 2.0))
    cy = max(0.0, min(1.0, y + h / 2.0))

    if cx < 0.33:
        col = "left"
    elif cx < 0.66:
        col = "center"
    else:
        col = "right"

    if cy < 0.33:
        row = "top"
    elif cy < 0.66:
        row = "mid"
    else:
        row = "bottom"

    if row == "mid" and col == "center":
        return "center"
    return f"{row}_{col}"


@dataclass
class DetectedPersonRecord:
    person_id: str
    region: str = "center"
    distance_m: Optional[float] = None
    confidence: float = 1.0
    last_seen_ts: float = field(default_factory=time.time)


@dataclass
class SoundEventRecord:
    direction_deg: float
    salience: float = 1.0
    ts: float = field(default_factory=time.time)


class SceneRegister:
    """Sliding-window ambient perception aggregator for autonomous decision making."""

    def __init__(self, window_s: float = 5.0) -> None:
        self.window_s = max(0.05, float(window_s))
        self._lock = threading.RLock()
        self._people: Dict[str, DetectedPersonRecord] = {}
        self._motion_energy: Dict[str, float] = {r: 0.0 for r in REGIONS_3X3}
        self._motion_energy_ts: Dict[str, float] = {r: 0.0 for r in REGIONS_3X3}
        self._sound_events: List[SoundEventRecord] = []
        self._last_change_ts: float = time.time()
        self._general_notes: str = ""

    def update_person(
        self,
        person_id: str | int,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        region: Optional[str] = None,
        distance_m: Optional[float] = None,
        confidence: float = 1.0,
    ) -> None:
        """Register or update a detected person in the scene."""
        pid_str = str(person_id).strip()
        if not pid_str:
            return

        if region is None and bbox is not None:
            region = bbox_to_region(*bbox)
        if region not in REGIONS_3X3:
            region = "center"

        with self._lock:
            now = time.time()
            self._people[pid_str] = DetectedPersonRecord(
                person_id=pid_str,
                region=region,
                distance_m=distance_m,
                confidence=confidence,
                last_seen_ts=now,
            )
            # Person presence adds motion/salience to that region
            self._motion_energy[region] = min(1.0, self._motion_energy.get(region, 0.0) + 0.3)
            self._motion_energy_ts[region] = now
            self._last_change_ts = now

    def update_motion_energy(self, grid_energies: Dict[str, float] | List[float]) -> None:
        """Update motion energy across regions (from frame-diff or sensors)."""
        with self._lock:
            now = time.time()
            if isinstance(grid_energies, list):
                for i, r in enumerate(REGIONS_3X3):
                    if i < len(grid_energies):
                        self._motion_energy[r] = max(0.0, min(1.0, float(grid_energies[i])))
                        self._motion_energy_ts[r] = now
            elif isinstance(grid_energies, dict):
                for r, val in grid_energies.items():
                    if r in self._motion_energy:
                        self._motion_energy[r] = max(0.0, min(1.0, float(val)))
                        self._motion_energy_ts[r] = now
            self._last_change_ts = now

    def update_sound_event(self, direction_deg: float, salience: float = 1.0) -> None:
        """Register an acoustic event with its Direction of Arrival."""
        with self._lock:
            now = time.time()
            self._sound_events.append(
                SoundEventRecord(
                    direction_deg=float(direction_deg),
                    salience=max(0.0, float(salience)),
                    ts=now,
                )
            )
            self._prune_expired_locked(now)
            self._last_change_ts = now

    def set_ambient_note(self, note: str) -> None:
        with self._lock:
            self._general_notes = str(note or "").strip()
            self._last_change_ts = time.time()

    def _prune_expired_locked(self, now: float) -> None:
        """Prune detections older than window_s and apply decay to motion energy."""
        cutoff = now - self.window_s
        self._people = {
            pid: rec for pid, rec in self._people.items() if rec.last_seen_ts >= cutoff
        }
        self._sound_events = [ev for ev in self._sound_events if ev.ts >= cutoff]

        # Decay motion energies smoothly if older than window_s
        for r in self._motion_energy:
            last_ts = self._motion_energy_ts.get(r, 0.0)
            if now - last_ts >= self.window_s:
                self._motion_energy[r] = 0.0

    def is_region_clear(self, region: str) -> bool:
        """Return True if the region has no recent people and low motion energy."""
        with self._lock:
            now = time.time()
            self._prune_expired_locked(now)
            if self._motion_energy.get(region, 0.0) > 0.35:
                return False
            for p in self._people.values():
                if p.region == region:
                    return False
            return True

    def get_clear_regions(self) -> List[str]:
        """Return list of regions that are currently empty and quiet."""
        with self._lock:
            now = time.time()
            self._prune_expired_locked(now)
            return [r for r in REGIONS_3X3 if self.is_region_clear(r)]

    def get_scene_state(self) -> Dict[str, Any]:
        """Return full structured scene snapshot."""
        with self._lock:
            now = time.time()
            self._prune_expired_locked(now)
            return {
                "people": [
                    {
                        "id": p.person_id,
                        "region": p.region,
                        "distance_m": p.distance_m,
                        "confidence": p.confidence,
                        "age_s": round(now - p.last_seen_ts, 1),
                    }
                    for p in self._people.values()
                ],
                "motion_energy": dict(self._motion_energy),
                "sound_events": [
                    {
                        "direction_deg": s.direction_deg,
                        "salience": s.salience,
                        "age_s": round(now - s.ts, 1),
                    }
                    for s in self._sound_events
                ],
                "clear_regions": self.get_clear_regions(),
                "last_change_ts": self._last_change_ts,
                "notes": self._general_notes,
            }

    def get_scene_summary(self) -> str:
        """Produce a concise, single-line natural language summary for LLM prompt injection."""
        with self._lock:
            now = time.time()
            self._prune_expired_locked(now)

            parts = []

            # 1. People summary
            if not self._people:
                parts.append("Oda/ortamda kimse görünmüyor (boş)")
            else:
                p_descs = []
                for p in self._people.values():
                    r_tr = REGION_NAMES_TR.get(p.region, p.region)
                    dist_str = f" ~{p.distance_m:.1f}m" if p.distance_m is not None else ""
                    p_descs.append(f"{p.person_id} ({r_tr}{dist_str})")
                parts.append(f"Görünen kişiler: {', '.join(p_descs)}")

            # 2. Motion / Activity
            active_regions = [
                REGION_NAMES_TR.get(r, r)
                for r, e in self._motion_energy.items()
                if e > 0.4
            ]
            if active_regions:
                parts.append(f"Hareketli bölgeler: {', '.join(active_regions)}")
            else:
                parts.append("Genel hareket sakin")

            # 3. Sound / DoA
            if self._sound_events:
                latest_sound = self._sound_events[-1]
                parts.append(f"Son ses yönü: {latest_sound.direction_deg:.0f}°")

            # 4. Quiet / Clear spots
            clear_spots = [
                REGION_NAMES_TR.get(r, r)
                for r in ["bottom_left", "bottom_right", "top_right", "top_left"]
                if self.is_region_clear(r)
            ]
            if clear_spots:
                parts.append(f"Sakin/boş köşeler: {', '.join(clear_spots[:2])}")

            if self._general_notes:
                parts.append(f"Not: {self._general_notes}")

            return " | ".join(parts)


__all__ = [
    "SceneRegister",
    "REGIONS_3X3",
    "REGION_NAMES_TR",
    "bbox_to_region",
    "DetectedPersonRecord",
    "SoundEventRecord",
]
