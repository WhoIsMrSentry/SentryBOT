from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..db import SocialDB


class FaceDescriptorsRepo:
    """Stores ORB / face_recognition / arbitrary descriptor blobs per person."""

    def __init__(self, db: "SocialDB") -> None:
        self.db = db

    def add(
        self,
        person_id: str,
        kind: str,
        blob: bytes,
        *,
        rows: int = 0,
        cols: int = 0,
        score: float = 0.0,
    ) -> int:
        now = time.time()
        with self.db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO face_descriptors (person_id, kind, blob, rows, cols, score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(person_id), str(kind), bytes(blob), int(rows), int(cols), float(score), now),
            )
            return int(cur.lastrowid or 0)

    def replace_for_person(
        self,
        person_id: str,
        kind: str,
        blob: bytes,
        *,
        rows: int = 0,
        cols: int = 0,
        score: float = 0.0,
    ) -> int:
        """Convenience: remove existing rows of ``kind`` for the person, then insert a new one."""
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM face_descriptors WHERE person_id = ? AND kind = ?",
                (str(person_id), str(kind)),
            )
            cur = conn.execute(
                """
                INSERT INTO face_descriptors (person_id, kind, blob, rows, cols, score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(person_id),
                    str(kind),
                    bytes(blob),
                    int(rows),
                    int(cols),
                    float(score),
                    time.time(),
                ),
            )
            return int(cur.lastrowid or 0)

    def list_for_person(self, person_id: str, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        if kind is None:
            rows = self.db.fetchall(
                "SELECT * FROM face_descriptors WHERE person_id = ? ORDER BY created_at DESC",
                (str(person_id),),
            )
        else:
            rows = self.db.fetchall(
                "SELECT * FROM face_descriptors WHERE person_id = ? AND kind = ? ORDER BY created_at DESC",
                (str(person_id), str(kind)),
            )
        return [{k: r[k] for k in r.keys()} for r in rows]

    def list_all_by_kind(self, kind: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Return ``[(person_id, row)]`` pairs for a given descriptor ``kind``.

        Useful for loading ORB descriptors into the in-memory FaceManager.
        """
        rows = self.db.fetchall(
            """
            SELECT fd.*, p.display_name AS display_name, p.canonical_name AS canonical_name
            FROM face_descriptors fd
            JOIN persons p ON p.id = fd.person_id
            WHERE fd.kind = ?
            ORDER BY fd.created_at DESC
            """,
            (str(kind),),
        )
        out: List[Tuple[str, Dict[str, Any]]] = []
        for r in rows:
            out.append((r["person_id"], {k: r[k] for k in r.keys()}))
        return out

    def delete_for_person(self, person_id: str, kind: Optional[str] = None) -> int:
        with self.db.transaction() as conn:
            if kind is None:
                cur = conn.execute(
                    "DELETE FROM face_descriptors WHERE person_id = ?",
                    (str(person_id),),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM face_descriptors WHERE person_id = ? AND kind = ?",
                    (str(person_id), str(kind)),
                )
            return int(cur.rowcount or 0)
