"""Multi-modal identity fusion (Face + Voice + RFID) with TTL and Bayesian/weighted scoring."""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any, Dict, List, Optional


@dataclass
class IdentitySignal:
    modality: str
    person_id: str
    confidence: float
    expires_at: float
    observed_at: float
    meta: Dict[str, Any]


class ActiveSpeakerResolver:
    """Fuses voice, face, and RFID signals within their active TTL windows."""

    MODALITY_WEIGHTS: Dict[str, float] = {
        "rfid": 0.50,
        "face": 0.30,
        "voice": 0.20,
    }
    CONSENSUS_BONUS: float = 0.15

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._signals: Dict[str, IdentitySignal] = {}

    def observe_face(
        self,
        person_id: str,
        confidence: float = 0.75,
        ttl_s: float = 15.0,
    ) -> Dict[str, Any]:
        return self._record("face", person_id, confidence, ttl_s)

    def observe_voice(
        self,
        person_id: str,
        confidence: float = 0.70,
        ttl_s: float = 20.0,
    ) -> Dict[str, Any]:
        return self._record("voice", person_id, confidence, ttl_s)

    def observe_rfid(
        self,
        person_id: str,
        uid: str = "",
        confidence: float = 0.95,
        ttl_s: float = 60.0,
    ) -> Dict[str, Any]:
        return self._record("rfid", person_id, confidence, ttl_s, meta={"uid": str(uid or "")})

    def _record(
        self,
        modality: str,
        person_id: str,
        confidence: float,
        ttl_s: float,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pid = str(person_id or "").strip()
        if not pid or pid.lower() == "unknown":
            return {"ok": False, "reason": "invalid_person_id"}
        mod = str(modality or "").strip().lower()
        if mod not in self.MODALITY_WEIGHTS:
            return {"ok": False, "reason": "unsupported_modality"}
        now = time.time()
        conf = max(0.0, min(1.0, float(confidence)))
        ttl = max(0.5, float(ttl_s))
        sig = IdentitySignal(
            modality=mod,
            person_id=pid,
            confidence=conf,
            expires_at=now + ttl,
            observed_at=now,
            meta=dict(meta or {}),
        )
        with self._lock:
            self._signals[mod] = sig
        return self.resolve()

    def _prune_expired_unlocked(self, now: float) -> None:
        expired = [m for m, s in self._signals.items() if s.expires_at <= now]
        for m in expired:
            self._signals.pop(m, None)

    def resolve(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            self._prune_expired_unlocked(now)
            if not self._signals:
                return {
                    "person_id": None,
                    "confidence": 0.0,
                    "modalities": [],
                    "active": False,
                }

            by_person: Dict[str, List[IdentitySignal]] = {}
            for sig in self._signals.values():
                by_person.setdefault(sig.person_id, []).append(sig)

            best_person: Optional[str] = None
            best_conf: float = -1.0
            best_mods: List[str] = []

            for pid, sigs in by_person.items():
                weighted_sum = 0.0
                weight_total = 0.0
                mods: List[str] = []
                for s in sigs:
                    w = self.MODALITY_WEIGHTS.get(s.modality, 0.2)
                    weighted_sum += s.confidence * w
                    weight_total += w
                    mods.append(s.modality)
                base_conf = (weighted_sum / weight_total) if weight_total > 0 else 0.0
                # Multi-modality agreement bonus (+0.15 when >=2 modalities agree)
                bonus = self.CONSENSUS_BONUS if len(sigs) >= 2 else 0.0
                fused_conf = min(1.0, round(base_conf + bonus, 4))
                # Tie-breaker: higher total modality weight, then higher fused confidence
                if (fused_conf, weight_total) > (best_conf, sum(self.MODALITY_WEIGHTS.get(m, 0.0) for m in best_mods)):
                    best_conf = fused_conf
                    best_person = pid
                    best_mods = sorted(mods)

            return {
                "person_id": best_person,
                "confidence": round(max(0.0, best_conf), 4),
                "modalities": best_mods,
                "active": best_person is not None and best_conf > 0.0,
            }

    def status(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            self._prune_expired_unlocked(now)
            signals_info = {
                mod: {
                    "person_id": sig.person_id,
                    "confidence": round(sig.confidence, 4),
                    "ttl_remaining_s": round(max(0.0, sig.expires_at - now), 2),
                    "meta": dict(sig.meta),
                }
                for mod, sig in self._signals.items()
            }
        resolved = self.resolve()
        return {
            "active_identity": resolved,
            "signals": signals_info,
        }

    def clear(self) -> None:
        with self._lock:
            self._signals.clear()


__all__ = ["ActiveSpeakerResolver", "IdentitySignal"]
