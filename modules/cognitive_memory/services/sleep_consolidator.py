"""Sleep & Memory Consolidation Engine (Gece Rüya / Uyku Fazı ve Ebbinghaus Unutma).

İnsanlar ve hayvanlar gibi, SentryBOT da şarjda veya gece dinlenme modundayken (Sleep Phase)
günün epizodik diyaloglarını ve izlenimlerini arka planda işler:
1. Ebbinghaus Forgetting: Önemsiz/düşük ağırlıklı günlük anıların güç derecesini (decay) azaltır.
2. Memory Consolidation (Rüya Fazı): Gün içindeki kullanıcı etkileşimlerini özetler,
   SocialDB ilişkilerini ve kullanıcı tercihlerini pekiştirir.
"""

from __future__ import annotations
import math
import time
from typing import Any, Dict, List, Optional

class SleepConsolidator:
    def __init__(self, social_db: Optional[Any] = None) -> None:
        self.social_db = social_db
        self._last_consolidation_ts = 0.0

    def compute_ebbinghaus_retention(self, initial_strength: float, elapsed_hours: float, stability: float = 24.0) -> float:
        """
        Ebbinghaus Unutma Eğrisi: R = e^(-t / S)
        R: Hatırlama gücü (retention, 0.0 - 1.0)
        t: Geçen süre (saat)
        S: Hafıza kararlılığı (stability, yüksek önem taşıyan anılar daha yavaş unutulur)
        """
        if elapsed_hours <= 0:
            return float(initial_strength)
        retention = math.exp(-elapsed_hours / max(1.0, stability))
        return round(float(initial_strength * retention), 3)

    def consolidate_session(
        self,
        interactions: List[Dict[str, Any]],
        current_time_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Şarj veya uyku modunda günün etkileşimlerini analiz edip özetler.
        """
        now = float(current_time_s if current_time_s is not None else time.time())
        if not interactions:
            return {"ok": True, "consolidated_count": 0, "summary": "no_interactions"}

        consolidated: List[Dict[str, Any]] = []
        user_mentions: Dict[str, int] = {}
        key_topics: List[str] = []

        for item in interactions:
            user = item.get("user") or item.get("speaker") or "owner"
            text = str(item.get("text") or item.get("content") or "")
            importance = float(item.get("importance", 1.0))
            ts = float(item.get("timestamp", now))
            age_hours = max(0.0, (now - ts) / 3600.0)

            # Ebbinghaus süzgeci: Önemsiz anılar zayıflar
            retained_strength = self.compute_ebbinghaus_retention(
                initial_strength=importance,
                elapsed_hours=age_hours,
                stability=48.0 if importance > 1.5 else 12.0,
            )

            # Sadece eşiğin üstünde kalan anılar uzun süreli hafızaya geçer
            if retained_strength >= 0.2:
                user_mentions[user] = user_mentions.get(user, 0) + 1
                consolidated.append({
                    "text": text,
                    "retained_strength": retained_strength,
                    "user": user,
                })

        self._last_consolidation_ts = now
        return {
            "ok": True,
            "consolidated_count": len(consolidated),
            "retained_ratio": round(len(consolidated) / max(1, len(interactions)), 2),
            "user_interactions": user_mentions,
            "timestamp": now,
        }
