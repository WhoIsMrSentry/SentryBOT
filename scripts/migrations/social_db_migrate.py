"""Migrate JSON-backed social/identity stores into ``data/social.sqlite3``.

Usage::

    python tools/social_db_migrate.py            # apply migrations and rename legacy files
    python tools/social_db_migrate.py --dry-run  # report planned actions without writing
    python tools/social_db_migrate.py --keep     # do not rename legacy JSON files

The script is idempotent: rerunning it inserts no duplicates because canonical
person names act as unique keys and identical descriptor/chat content is
deduplicated. Legacy files are renamed to ``<name>.legacy.json`` after a
successful pass unless ``--keep`` is set.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make the project root importable when run as a script.
_THIS = Path(__file__).resolve()
_ROOT = _THIS.parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.cognitive_memory.db import SocialDB  # noqa: E402


def _try_numpy():
    """Lazily import numpy. Returns the module or ``None``.

    Honours ``SENTRYBOT_DISABLE_NUMPY`` for environments where ``import numpy``
    is unstable (e.g. experimental Python 3.14 + MINGW builds on Windows).
    """
    if str(os.getenv("SENTRYBOT_DISABLE_NUMPY", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return None
    try:
        import numpy as _np  # type: ignore

        return _np
    except Exception:
        return None

logger = logging.getLogger("social_db_migrate")


def _load_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("failed to read %s: %s", path, exc)
        return None


def _legacy_rename(path: Path, dry_run: bool, keep: bool) -> None:
    if dry_run or keep or not path.exists():
        return
    legacy = path.with_suffix(path.suffix + ".legacy")
    if legacy.exists():
        legacy.unlink()
    path.rename(legacy)
    logger.info("renamed %s -> %s", path.name, legacy.name)


def _ensure_person(db: SocialDB, name: str, *, person_id: Optional[str] = None) -> str:
    rec = db.persons.upsert(name=name, person_id=person_id)
    return str(rec.get("id") or "")


def migrate_person_identity(db: SocialDB, *, dry_run: bool, keep: bool) -> int:
    """Import ``modules/vlm_bridge/data/person_identity.json``."""
    path = _ROOT / "modules" / "vlm_bridge" / "data" / "person_identity.json"
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return 0

    imported = 0
    for pid, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name") or "Unknown")
        if dry_run:
            logger.info("[dry] person_identity -> %s (%s)", name, pid)
            imported += 1
            continue
        rec = db.persons.upsert(
            name=name,
            person_id=str(pid),
            recognition_level=int(payload.get("recognition_level", 0) or 0),
            relationship=str(payload.get("relationship", "unknown") or "unknown"),
            is_owner=bool(payload.get("owner_priority")) or int(payload.get("recognition_level", 0) or 0) >= 5,
            owner_priority=bool(payload.get("owner_priority")),
            trust_score=float(payload.get("trust_score", 0.0) or 0.0),
            extra_patch={
                "appearance_notes": payload.get("appearance_notes", []),
                "voice_notes": payload.get("voice_notes", []),
                "first_seen": payload.get("first_seen", ""),
                "last_seen": payload.get("last_seen", ""),
                "seen_count": int(payload.get("seen_count", 0) or 0),
            },
        )
        # Conversation notes -> chat_episodes (role 'note')
        notes = payload.get("conversation_notes", [])
        if isinstance(notes, list):
            for note in notes:
                if not isinstance(note, str) or not note.strip():
                    continue
                db.chat_episodes.append(person_id=rec["id"], role="note", text=note.strip())
        imported += 1

    if imported:
        _legacy_rename(path, dry_run, keep)
    return imported


def _descriptor_to_blob(desc_list: List[List[int]]) -> Optional[tuple[bytes, int, int]]:
    """Validate and serialise an ORB descriptor matrix to a flat ``uint8`` blob.

    Returns ``(blob, rows, cols)`` or ``None`` when the matrix is malformed.
    Always uses pure Python; numpy is only consulted as a fast-path when present.
    """
    if not isinstance(desc_list, list) or not desc_list:
        return None
    np_mod = _try_numpy()
    if np_mod is not None:
        try:
            arr = np_mod.array(desc_list, dtype=np_mod.uint8)
        except Exception:
            arr = None
        if arr is not None and arr.ndim == 2 and arr.shape[1] == 32:
            return arr.tobytes(), int(arr.shape[0]), int(arr.shape[1])

    rows = 0
    out = bytearray()
    for row in desc_list:
        if not isinstance(row, list) or len(row) != 32:
            return None
        for v in row:
            try:
                out.append(int(v) & 0xFF)
            except Exception:
                return None
        rows += 1
    if rows == 0:
        return None
    return bytes(out), rows, 32


def migrate_faces(db: SocialDB, *, dry_run: bool, keep: bool) -> int:
    """Import ``data/faces.json`` ORB descriptors into ``face_descriptors``."""
    path = _ROOT / "data" / "faces.json"
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return 0

    imported = 0
    for name, payload in raw.items():
        desc_list: Any = None
        if isinstance(payload, dict):
            desc_list = payload.get("descriptors")
        elif isinstance(payload, list):
            desc_list = payload

        parsed = _descriptor_to_blob(desc_list)
        if parsed is None:
            continue
        blob, rows, cols = parsed

        if dry_run:
            logger.info("[dry] faces -> %s (rows=%d, cols=%d)", name, rows, cols)
            imported += 1
            continue

        pid = _ensure_person(db, name)
        if not pid:
            continue
        db.face_descriptors.replace_for_person(
            person_id=pid,
            kind="orb",
            blob=blob,
            rows=rows,
            cols=cols,
            score=1.0,
        )
        imported += 1

    if imported:
        _legacy_rename(path, dry_run, keep)
    return imported


def migrate_people_memory(db: SocialDB, *, dry_run: bool, keep: bool) -> int:
    """Import ``data/people_memory.json`` chat history."""
    path = _ROOT / "data" / "people_memory.json"
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return 0

    imported = 0
    for name, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        chats = payload.get("chats", [])
        if not isinstance(chats, list) or not chats:
            continue

        if dry_run:
            logger.info("[dry] people_memory -> %s (%d chats)", name, len(chats))
            imported += 1
            continue

        pid = _ensure_person(db, name)
        if not pid:
            continue
        db.chat_episodes.prune_for_person(pid, keep_last=0)
        for chat in chats:
            if not isinstance(chat, dict):
                continue
            db.chat_episodes.append(
                person_id=pid,
                role=str(chat.get("role", "user")),
                text=str(chat.get("text", "")),
                ts=float(chat.get("ts", time.time()) or time.time()),
            )
        summary = payload.get("last_summary")
        if isinstance(summary, dict) and summary.get("text"):
            db.moments.add_or_boost(
                person_id=pid,
                text=str(summary.get("text") or ""),
                salience=0.7,
                kind="summary",
            )
        imported += 1

    if imported:
        _legacy_rename(path, dry_run, keep)
    return imported


def migrate_relationship_memory(db: SocialDB, *, dry_run: bool, keep: bool) -> int:
    """Import ``modules/autonomy/data/relationship_memory.json``."""
    path = _ROOT / "modules" / "autonomy" / "data" / "relationship_memory.json"
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return 0

    imported = 0
    for _key, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        name = str(payload.get("name", "")).strip() or "Unknown"
        is_owner = bool(payload.get("is_owner", False))
        last_emotion = str(payload.get("last_emotion", "") or "")
        seen_count = int(payload.get("seen_count", 0) or 0)

        if dry_run:
            logger.info("[dry] relationship_memory -> %s (seen=%d)", name, seen_count)
            imported += 1
            continue

        rec = db.persons.upsert(
            name=name,
            is_owner=is_owner,
            owner_priority=is_owner,
            last_emotion=last_emotion,
        )
        pid = rec.get("id") or ""
        if not pid:
            continue

        # Replay seen_count by raising counter once.
        if seen_count:
            try:
                db.execute(
                    "UPDATE persons SET seen_count = MAX(seen_count, ?) WHERE id = ?",
                    (int(seen_count), pid),
                )
            except Exception:
                pass

        chat_history = payload.get("chat_history", [])
        if isinstance(chat_history, list):
            db.chat_episodes.prune_for_person(pid, keep_last=0)
            for entry in chat_history:
                if not isinstance(entry, dict):
                    continue
                db.chat_episodes.append(
                    person_id=pid,
                    role=str(entry.get("role", "user")),
                    text=str(entry.get("text", "")),
                    ts=float(entry.get("ts", time.time()) or time.time()),
                )

        preferences = payload.get("preferences", {})
        if isinstance(preferences, dict):
            for key, value in preferences.items():
                if isinstance(value, list):
                    db.relationships.set(pid, str(key), ",".join(str(v) for v in value))
                elif value:
                    db.relationships.set(pid, str(key), str(value))

        moments = payload.get("moments", [])
        if isinstance(moments, list):
            for moment in moments:
                if not isinstance(moment, dict):
                    continue
                text = str(moment.get("text", "") or "").strip()
                if not text:
                    continue
                db.moments.add_or_boost(
                    person_id=pid,
                    text=text,
                    salience=float(moment.get("score", 0.1) or 0.1),
                    kind=str(moment.get("kind", "note") or "note"),
                )

        imported += 1

    if imported:
        _legacy_rename(path, dry_run, keep)
    return imported


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report planned actions without writing")
    parser.add_argument("--keep", action="store_true", help="do not rename legacy JSON files")
    parser.add_argument("--db", default="data/social.sqlite3", help="target SQLite path")
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="enable debug logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    db = SocialDB(path=args.db, auto_migrate=True)
    try:
        total = 0
        total += migrate_person_identity(db, dry_run=args.dry_run, keep=args.keep)
        total += migrate_faces(db, dry_run=args.dry_run, keep=args.keep)
        total += migrate_people_memory(db, dry_run=args.dry_run, keep=args.keep)
        total += migrate_relationship_memory(db, dry_run=args.dry_run, keep=args.keep)
        logger.info("migration finished; records touched: %d", total)
        stats = db.snapshot_stats()
        for k, v in sorted(stats.items()):
            logger.info("  %s = %s", k, v)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
