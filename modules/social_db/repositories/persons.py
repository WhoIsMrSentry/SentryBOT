from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


def _canon(name: str) -> str:
    return str(name or "").strip().lower()


class PersonsRepo:
    """CRUD layer for the ``persons`` table."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def upsert(
        self,
        name: str,
        *,
        person_id: Optional[str] = None,
        recognition_level: Optional[int] = None,
        relationship: Optional[str] = None,
        is_owner: Optional[bool] = None,
        owner_priority: Optional[bool] = None,
        trust_score: Optional[float] = None,
        last_emotion: Optional[str] = None,
        last_distance_m: Optional[float] = None,
        increment_seen: bool = False,
        extra_patch: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create or update a person record keyed by canonical name."""
        canonical = _canon(name)
        if not canonical:
            canonical = "unknown"
        display = str(name or "").strip() or "Unknown"
        now = time.time()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM persons WHERE canonical_name = ?",
                (canonical,),
            ).fetchone()
            if row is None:
                pid = person_id or uuid.uuid4().hex[:10]
                extra = json.dumps(extra_patch or {}, ensure_ascii=True)
                conn.execute(
                    """
                    INSERT INTO persons (
                        id, canonical_name, display_name, recognition_level,
                        relationship, is_owner, owner_priority, seen_count,
                        trust_score, last_emotion, last_distance_m,
                        first_seen_at, last_seen_at, created_at, updated_at, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        canonical,
                        display,
                        int(recognition_level or 0),
                        str(relationship or "unknown"),
                        1 if is_owner else 0,
                        1 if owner_priority else 0,
                        1 if increment_seen else 0,
                        float(trust_score or 0.0),
                        str(last_emotion or ""),
                        float(last_distance_m) if last_distance_m is not None else None,
                        now,
                        now,
                        now,
                        now,
                        extra,
                    ),
                )
                return self._fetch_locked(conn, canonical)

            pid = row["id"]
            updates: list[str] = ["updated_at = ?", "last_seen_at = ?"]
            params: list[Any] = [now, now]
            if display and row["display_name"] != display:
                updates.append("display_name = ?")
                params.append(display)
            if recognition_level is not None:
                updates.append("recognition_level = ?")
                params.append(int(recognition_level))
            if relationship is not None:
                updates.append("relationship = ?")
                params.append(str(relationship))
            if is_owner is not None:
                updates.append("is_owner = ?")
                params.append(1 if is_owner else 0)
            if owner_priority is not None:
                updates.append("owner_priority = ?")
                params.append(1 if owner_priority else 0)
            if trust_score is not None:
                updates.append("trust_score = ?")
                params.append(float(trust_score))
            if last_emotion is not None:
                updates.append("last_emotion = ?")
                params.append(str(last_emotion))
            if last_distance_m is not None:
                updates.append("last_distance_m = ?")
                params.append(float(last_distance_m))
            if increment_seen:
                updates.append("seen_count = seen_count + 1")
            if extra_patch:
                try:
                    current_extra = json.loads(row["extra_json"] or "{}")
                except Exception:
                    current_extra = {}
                current_extra.update(extra_patch)
                updates.append("extra_json = ?")
                params.append(json.dumps(current_extra, ensure_ascii=True))
            params.append(pid)
            conn.execute(
                f"UPDATE persons SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            return self._fetch_locked(conn, canonical)

    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        canonical = _canon(name)
        if not canonical:
            return None
        row = self.db.fetchone(
            "SELECT * FROM persons WHERE canonical_name = ?", (canonical,)
        )
        return self._row_to_dict(row) if row else None

    def get_by_id(self, person_id: str) -> Optional[Dict[str, Any]]:
        if not person_id:
            return None
        row = self.db.fetchone("SELECT * FROM persons WHERE id = ?", (person_id,))
        return self._row_to_dict(row) if row else None

    def list_all(self) -> List[Dict[str, Any]]:
        rows = self.db.fetchall("SELECT * FROM persons ORDER BY last_seen_at DESC")
        return [self._row_to_dict(r) for r in rows]

    def get_owner(self) -> Optional[Dict[str, Any]]:
        row = self.db.fetchone(
            "SELECT * FROM persons WHERE is_owner = 1 OR owner_priority = 1 OR recognition_level >= 5 ORDER BY recognition_level DESC LIMIT 1"
        )
        return self._row_to_dict(row) if row else None

    def set_owner(self, name: str) -> Dict[str, Any]:
        return self.upsert(
            name,
            recognition_level=5,
            relationship="owner",
            is_owner=True,
            owner_priority=True,
        )

    def top_people(self, limit: int = 3) -> List[Dict[str, Any]]:
        rows = self.db.fetchall(
            "SELECT * FROM persons ORDER BY seen_count DESC, last_seen_at DESC LIMIT ?",
            (max(1, int(limit)),),
        )
        return [self._row_to_dict(r) for r in rows]

    def adjust_trust(
        self,
        person_id: str,
        delta: float,
        *,
        min_score: float = 0.0,
        max_score: float = 1.0,
    ) -> float:
        """Nudge trust_score by delta and return the clamped new value."""
        rec = self.get_by_id(person_id)
        if not rec:
            return 0.0
        new_score = max(min_score, min(max_score, float(rec.get("trust_score", 0.0)) + float(delta)))
        updated = self.upsert(name=rec.get("display_name") or rec.get("canonical_name") or "Unknown", trust_score=new_score)
        return float(updated.get("trust_score", new_score))

    def delete(self, person_id: str) -> bool:
        with self.db.transaction() as conn:
            cur = conn.execute("DELETE FROM persons WHERE id = ?", (person_id,))
            return cur.rowcount > 0

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        if row is None:
            return {}
        out: Dict[str, Any] = {k: row[k] for k in row.keys()}
        try:
            out["extra"] = json.loads(out.pop("extra_json") or "{}")
        except Exception:
            out["extra"] = {}
            out.pop("extra_json", None)
        out["is_owner"] = bool(out.get("is_owner"))
        out["owner_priority"] = bool(out.get("owner_priority"))
        return out

    def _fetch_locked(self, conn: Any, canonical: str) -> Dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM persons WHERE canonical_name = ?", (canonical,)
        ).fetchone()
        return self._row_to_dict(row) if row else {}
