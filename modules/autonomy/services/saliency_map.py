"""Saliency Map Engine (Seçici Dikkat Motoru).

Robotun etrafındaki yüzlerce duyusal uyarıcıdan (görsel yüzler, hareketler, sesler)
en önemli olanını seçip robotun dikkat odağını (Focus of Attention) belirler.

Öncelik Hiyerarşisi:
1. Tanınan Sahip (Recognized Owner) - Ağırlık: 1.0
2. Yeni/Bilinmeyen İnsan Yüzü - Ağırlık: 0.85
3. Yüksek Enerjili Ses / Konuşma - Ağırlık: 0.70
4. Görsel Hareket (Motion Vector) - Ağırlık: 0.40
5. Ortam Taraması (Ambient Scan / Idle) - Ağırlık: 0.10
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class SaliencyTarget:
    target_type: str  # "person", "face", "sound", "motion", "idle"
    priority_score: float
    pan_hint: Optional[int] = None
    tilt_hint: Optional[int] = None
    label: str = ""
    metadata: Dict[str, Any] = None

class SaliencyMapEngine:
    def __init__(self) -> None:
        self._current_target: Optional[SaliencyTarget] = None
        self._target_locked_until = 0.0
        self._lock_duration_s = 2.0  # Bir hedefe odaklanınca en az 2s takip et (titremeyi önle)

    def evaluate(
        self,
        faces: Optional[List[Dict[str, Any]]] = None,
        sound_event: Optional[Dict[str, Any]] = None,
        motion: Optional[Dict[str, Any]] = None,
    ) -> SaliencyTarget:
        now = time.time()
        candidates: List[SaliencyTarget] = []

        # 1. Yüzleri değerlendir
        for face in (faces or []):
            is_owner = bool(face.get("is_owner") or face.get("recognized"))
            score = 1.0 if is_owner else 0.85
            cx = face.get("center_x", 0.5)
            # Normalize 0..1 to servo pan 45..135
            pan = int(135 - (cx * 90))
            candidates.append(
                SaliencyTarget(
                    target_type="person" if is_owner else "face",
                    priority_score=score,
                    pan_hint=pan,
                    tilt_hint=95,
                    label=face.get("name", "unknown_person"),
                    metadata=face,
                )
            )

        # 2. Ses olayını değerlendir
        if sound_event and sound_event.get("detected"):
            energy = float(sound_event.get("energy", 0.7))
            angle = float(sound_event.get("angle", 0.0))
            # Angle -90..+90 to pan 45..135
            pan = int(max(45, min(135, 90 + angle)))
            candidates.append(
                SaliencyTarget(
                    target_type="sound",
                    priority_score=0.70 * energy,
                    pan_hint=pan,
                    tilt_hint=90,
                    label="audio_source",
                    metadata=sound_event,
                )
            )

        # 3. Görsel hareketi değerlendir
        if motion and motion.get("active"):
            candidates.append(
                SaliencyTarget(
                    target_type="motion",
                    priority_score=0.40,
                    pan_hint=motion.get("pan"),
                    tilt_hint=motion.get("tilt"),
                    label="motion_target",
                    metadata=motion,
                )
            )

        # Aday yoksa idle
        if not candidates:
            return SaliencyTarget(
                target_type="idle",
                priority_score=0.10,
                pan_hint=90,
                tilt_hint=90,
                label="idle_center",
                metadata={},
            )

        # En yüksek skorlu adayı bul
        best = max(candidates, key=lambda c: c.priority_score)

        # Eğer mevcut bir kilit varsa ve yeni gelen hedef belirgin şekilde daha önemli değilse kilidi koru
        if self._current_target and now < self._target_locked_until:
            if best.priority_score <= self._current_target.priority_score + 0.2:
                return self._current_target

        self._current_target = best
        self._target_locked_until = now + self._lock_duration_s
        return best
