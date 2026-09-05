"""Reinforcement from lightweight interaction signals (praise, rudeness).

Maps appraisal events into durable relationship changes: trust_score nudges
and salient moments on the speaker's social record. Pure and config-driven so
it runs on PC with an in-memory SocialDB.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class InteractionFeedbackLearner:
    # Appraisal event -> (trust_delta, moment_text, moment_salience).
    _DEFAULT_DELTAS: Dict[str, tuple] = {
        "user_praise": (0.08, "positive interaction", 0.5),
        "user_rude": (-0.12, "negative interaction", 0.55),
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None, social_db: Any = None) -> None:
        cfg = config if isinstance(config, dict) else {}
        self.enabled = bool(cfg.get("enabled", True))
        self.trust_min = float(cfg.get("trust_min", 0.0))
        self.trust_max = float(cfg.get("trust_max", 1.0))
        self._social_db = social_db
        raw = cfg.get("deltas", {}) if isinstance(cfg.get("deltas", {}), dict) else {}
        self._deltas = dict(self._DEFAULT_DELTAS)
        for key, val in raw.items():
            if isinstance(val, dict):
                self._deltas[str(key)] = (
                    float(val.get("trust", self._DEFAULT_DELTAS.get(key, (0, "", 0))[0])),
                    str(val.get("moment", self._DEFAULT_DELTAS.get(key, ("", "", 0))[1])),
                    float(val.get("salience", self._DEFAULT_DELTAS.get(key, (0, "", 0))[2])),
                )

    def apply(self, event: str, speaker: Optional[str] = None, *, text: str = "") -> Optional[float]:
        """Apply feedback for an appraisal event; returns new trust_score or None."""
        if not self.enabled or not event or not speaker:
            return None
        spk = str(speaker).strip()
        if not spk or spk.lower() in {"unknown", "none"}:
            return None
        spec = self._deltas.get(str(event))
        if not spec:
            return None
        trust_delta, moment_txt, salience = spec
        db = self._get_db()
        if db is None:
            return None
        try:
            person = db.persons.upsert(name=spk)
            pid = person.get("id") if isinstance(person, dict) else None
            if not pid:
                return None
            new_trust = db.persons.adjust_trust(pid, trust_delta, min_score=self.trust_min, max_score=self.trust_max)
            snippet = str(text or "").strip()[:120]
            label = moment_txt if not snippet else f"{moment_txt}: {snippet}"
            db.moments.add_or_boost(person_id=pid, text=label, salience=salience)
            try:
                db.interaction_events.log(event, payload={"person_id": pid, "text": snippet})
            except Exception:
                pass
            return new_trust
        except Exception:
            return None

    def _get_db(self):
        if self._social_db is not None:
            return self._social_db
        try:
            from modules.cognitive_memory import get_default as _social_default

            self._social_db = _social_default()
        except Exception:
            self._social_db = None
        return self._social_db


__all__ = ["InteractionFeedbackLearner"]
