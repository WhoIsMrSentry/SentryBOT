"""Sleep & Memory Consolidation Engine (Uyku/Bakım Fazı & Ebbinghaus Unutma).

Şarj veya dinlenme modundayken günlük epizodik diyalogları ve izlenimleri işler:
1. Ebbinghaus Forgetting: ``SocialDB.moments.decay()`` üzerinden düşük ağırlıklı anıları azaltır.
2. Memory Consolidation: Gün içi özetleri ``ChatRAG.remember_day_summary()`` ve
   ``WorldMemoryRAG.consolidate_memories()`` üzerine yazar; bekleyen gömlemeleri (backfill)
   ve güvenli SQLite `.backup()` yedeklerini alır.
"""

from __future__ import annotations

import datetime
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional


class SleepConsolidator:
    def __init__(
        self,
        social_db: Optional[Any] = None,
        chat_rag: Optional[Any] = None,
        world_rag: Optional[Any] = None,
    ) -> None:
        self.social_db = social_db
        self.chat_rag = chat_rag
        self.world_rag = world_rag
        self._last_consolidation_ts = 0.0

    def compute_ebbinghaus_retention(
        self,
        initial_strength: float,
        elapsed_hours: float,
        stability: float = 24.0,
    ) -> float:
        """Ebbinghaus Unutma Eğrisi: R = initial * e^(-t / S)."""
        if elapsed_hours <= 0:
            return float(initial_strength)
        retention = math.exp(-elapsed_hours / max(1.0, stability))
        return round(float(initial_strength * retention), 3)

    def consolidate_session(
        self,
        interactions: List[Dict[str, Any]],
        current_time_s: Optional[float] = None,
        *,
        person_id: Optional[str] = None,
        day: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Şarj veya uyku modunda günün etkileşimlerini analiz edip SocialDB/ChatRAG'e işler."""
        now = float(current_time_s if current_time_s is not None else time.time())
        if not interactions:
            return {"ok": True, "consolidated_count": 0, "summary": "no_interactions"}

        consolidated: List[Dict[str, Any]] = []
        user_mentions: Dict[str, int] = {}

        for item in interactions:
            user = item.get("user") or item.get("speaker") or "owner"
            text = str(item.get("text") or item.get("content") or "")
            importance = float(item.get("importance", 1.0))
            ts = float(item.get("timestamp", now))
            age_hours = max(0.0, (now - ts) / 3600.0)

            retained_strength = self.compute_ebbinghaus_retention(
                initial_strength=importance,
                elapsed_hours=age_hours,
                stability=48.0 if importance > 1.5 else 12.0,
            )

            if retained_strength >= 0.2:
                user_mentions[user] = user_mentions.get(user, 0) + 1
                consolidated.append(
                    {
                        "text": text,
                        "retained_strength": retained_strength,
                        "user": user,
                    }
                )

        summary_day = day or datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
        decayed_moments = 0
        summary_saved = False

        if self.social_db is not None and person_id:
            try:
                decayed_moments = int(self.social_db.moments.decay(person_id))
            except Exception:
                decayed_moments = 0

        if self.chat_rag is not None and consolidated:
            target_pid = person_id or next(iter(user_mentions), "owner")
            summary_lines = [f"- {c['user']}: {c['text'][:160]}" for c in consolidated[:8] if c["text"].strip()]
            if summary_lines:
                try:
                    summary_saved = bool(
                        self.chat_rag.remember_day_summary(
                            person_id=target_pid,
                            day=summary_day,
                            text="\n".join(summary_lines),
                        )
                    )
                except Exception:
                    summary_saved = False

        self._last_consolidation_ts = now
        return {
            "ok": True,
            "consolidated_count": len(consolidated),
            "retained_ratio": round(len(consolidated) / max(1, len(interactions)), 2),
            "user_interactions": user_mentions,
            "decayed_moments": decayed_moments,
            "summary_saved": summary_saved,
            "timestamp": now,
        }

    def run_maintenance(
        self,
        *,
        person_id: Optional[str] = None,
        backfill_batch: int = 32,
        backup_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        """Run full idle/charging maintenance: moment decay, RAG consolidation, embedding backfill and DB backup."""
        decayed_total = 0
        if self.social_db is not None:
            if person_id:
                decayed_total += int(self.social_db.moments.decay(person_id))
            else:
                for rec in self.social_db.persons.list_all():
                    pid = str(rec.get("id") or "")
                    if pid:
                        decayed_total += int(self.social_db.moments.decay(pid))

        chat_backfilled = 0
        if self.chat_rag is not None and hasattr(self.chat_rag, "backfill_embeddings"):
            chat_backfilled = int(self.chat_rag.backfill_embeddings(batch_size=backfill_batch))

        world_consolidated = 0
        world_backfilled = 0
        if self.world_rag is not None:
            if hasattr(self.world_rag, "consolidate_memories"):
                world_consolidated = int((self.world_rag.consolidate_memories() or {}).get("consolidated", 0))
            if hasattr(self.world_rag, "backfill_embeddings"):
                world_backfilled = int(self.world_rag.backfill_embeddings(batch_size=backfill_batch))

        backups: List[str] = []
        if backup_dir is not None:
            bdir = Path(backup_dir)
            if self.social_db is not None and hasattr(self.social_db, "backup"):
                backups.append(str(self.social_db.backup(bdir / "social.sqlite3.backup")))
            if self.chat_rag is not None and hasattr(self.chat_rag, "backup"):
                backups.append(str(self.chat_rag.backup(bdir / "chat_rag.sqlite3.backup")))
            if self.world_rag is not None and hasattr(self.world_rag, "backup"):
                backups.append(str(self.world_rag.backup(bdir / "world_memory.sqlite3.backup")))

        self._last_consolidation_ts = time.time()
        return {
            "ok": True,
            "decayed_moments": decayed_total,
            "chat_backfilled": chat_backfilled,
            "world_consolidated": world_consolidated,
            "world_backfilled": world_backfilled,
            "backups": backups,
            "timestamp": self._last_consolidation_ts,
        }
