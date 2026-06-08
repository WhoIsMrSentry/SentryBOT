"""Affective appraisal engine.

Maps *semantic events* (e.g. ``user_rude``, ``owner_returned``) onto mood-axis
deltas so the robot's feelings have causes rather than only time-based decay.

Rules are config-driven (``config/appraisal.yml``) and can be overridden by the
autonomy config under ``defaults.appraisal.rules``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger("autonomy.appraisal")

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "appraisal.yml"

# Minimal built-in defaults so the engine works even without the YAML file.
_DEFAULT_RULES: Dict[str, Dict[str, float]] = {
    "owner_returned": {"happiness": 22, "anger": -12, "fear": -10},
    "user_praise": {"happiness": 18, "anger": -10},
    "user_rude": {"anger": 32, "happiness": -12},
    "command_failed": {"anger": 12, "fear": 6},
    "loud_noise": {"fear": 22, "anger": 5},
    "new_person": {"curiosity": 12},
    "petted": {"happiness": 16, "anger": -16},
}


class AffectiveAppraisal:
    """Turns events into mood deltas and applies them to a mood manager."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.rules: Dict[str, Dict[str, float]] = dict(_DEFAULT_RULES)
        self._load_yaml_rules()
        # Allow an autonomy-config override to win over file/defaults.
        override = ((config or {}).get("defaults", {}) or {}).get("appraisal", {}) or {}
        file_rules = override.get("rules")
        if isinstance(file_rules, dict):
            self._merge_rules(file_rules)

    def _load_yaml_rules(self) -> None:
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            rules = data.get("rules")
            if isinstance(rules, dict):
                self._merge_rules(rules)
        except FileNotFoundError:
            logger.debug("appraisal.yml not found, using built-in defaults")
        except Exception as exc:
            logger.warning("failed to load appraisal rules: %s", exc)

    def _merge_rules(self, rules: Dict[str, Any]) -> None:
        for event, deltas in rules.items():
            if not isinstance(deltas, dict):
                continue
            clean = {}
            for axis, value in deltas.items():
                try:
                    clean[str(axis)] = float(value)
                except (TypeError, ValueError):
                    continue
            if clean:
                self.rules[str(event).strip().lower()] = clean

    def known_events(self):
        return sorted(self.rules.keys())

    def appraise(self, event: str, intensity: float = 1.0) -> Dict[str, float]:
        """Return scaled mood deltas for an event (empty dict if unknown)."""
        deltas = self.rules.get(str(event).strip().lower())
        if not deltas:
            return {}
        factor = max(0.0, float(intensity))
        return {axis: value * factor for axis, value in deltas.items()}

    def apply(self, mood: Any, event: str, intensity: float = 1.0) -> Optional[str]:
        """Apply an event's deltas to ``mood``; returns the event if it matched."""
        deltas = self.appraise(event, intensity)
        if not deltas:
            return None
        for axis, delta in deltas.items():
            try:
                mood.modify(axis, delta)
            except Exception:
                continue
        return str(event).strip().lower()


__all__ = ["AffectiveAppraisal"]
