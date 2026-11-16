from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..utils import resolve_repo_path

KIND_ALIASES: Dict[str, str] = {
    "person": "people",
    "people": "people",
    "owner": "people",
    "user": "people",
    "place": "places",
    "location": "places",
    "room": "places",
    "places": "places",
    "object": "objects",
    "objects": "objects",
    "thing": "objects",
    "item": "objects",
    "event": "events",
    "events": "events",
    "observation": "observations",
    "observations": "observations",
    "note": "observations",
    "habit": "habits",
    "habits": "habits",
    "routine": "habits",
}


WORLD_MEMORY_PERSISTENCE_TRUTH_CONTRACT = True
WORLD_MEMORY_PERSISTENCE_ROLE = "local_json_semantic_memory_store"
SCHEMA: Dict[str, Dict[str, Any]] = {
    "people": {"description": "known or recently observed people", "merge_by": "name"},
    "places": {"description": "rooms, locations and stable zones", "merge_by": "name"},
    "objects": {"description": "known or recently observed objects", "merge_by": "name"},
    "events": {"description": "time-based semantic events", "merge_by": "name+source"},
    "observations": {"description": "raw semantic observations", "merge_by": "summary+source"},
    "habits": {"description": "learned or declared repeated patterns", "merge_by": "name"},
}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return " ".join(text.split())


def _normalize_kind(kind: Any) -> str:
    key = _clean_text(kind or "observation").lower().replace("-", "_")
    return KIND_ALIASES.get(key, KIND_ALIASES.get(key.rstrip("s"), "observations"))


def _slug(text: str) -> str:
    cleaned = []
    for ch in text.lower():
        if ch.isalnum():
            cleaned.append(ch)
        elif cleaned and cleaned[-1] != "_":
            cleaned.append("_")
    value = "".join(cleaned).strip("_")
    return value or "unnamed"


class WorldMemory:
    """Thread-safe semantic world-memory facade with expiry pruning and optional RAG/SocialDB backing."""

    DEFAULTS: Dict[str, Any] = {
        "enabled": True,
        "max_entries_per_kind": 200,
        "recent_limit": 20,
        "decay_half_life_s": 86400.0,
        "persistence_enabled": True,
        "storage_path": ".sentrybot_state/world_memory.json",
        "save_interval_s": 0.0,
    }

    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        raw = cfg if isinstance(cfg, dict) else {}
        self.cfg: Dict[str, Any] = dict(self.DEFAULTS)
        self.cfg.update(raw)
        self._lock = threading.RLock()
        self._store: Dict[str, Dict[str, Dict[str, Any]]] = {kind: {} for kind in SCHEMA}
        self._history: List[Dict[str, Any]] = []
        self._last_persist_error = ""
        self._loaded_from_disk = False
        self._dirty = False
        self._last_save_ts = 0.0
        self._rag: Any = raw.get("rag_backing")
        self._social_db: Any = raw.get("social_db")
        self._load()

    def set_rag_backing(self, rag: Any) -> None:
        """Attach an optional shared WorldMemoryRAG instance for dual-write synchronization."""
        with self._lock:
            self._rag = rag

    def _is_expired(self, item: Dict[str, Any], now: float) -> bool:
        exp = _as_float(item.get("expiry"), 0.0)
        return exp > 0.0 and now >= exp

    def _purge_expired_unlocked(self, now: float) -> int:
        removed = 0
        for bucket in self._store.values():
            expired_keys = [k for k, v in bucket.items() if self._is_expired(v, now)]
            for k in expired_keys:
                bucket.pop(k, None)
                removed += 1
        if removed:
            self._dirty = True
        return removed

    def _retire_superseded_unlocked(self, supersedes: str) -> None:
        target = _clean_text(supersedes)
        if not target:
            return
        if ":" in target:
            kind_raw, key_raw = target.split(":", 1)
            bucket = self._store.get(_normalize_kind(kind_raw), {})
            if key_raw in bucket:
                bucket.pop(key_raw, None)
                return
        for bucket in self._store.values():
            to_del = [k for k, v in bucket.items() if v.get("id") == target]
            for k in to_del:
                bucket.pop(k, None)

    def _sync_to_backing(self, item: Dict[str, Any], *, source: str = "api") -> None:
        rag = self._rag
        if rag is None and bool(self.cfg.get("sync_to_rag", False)):
            try:
                from .world_memory_rag import get_default as _get_rag_default

                rag = _get_rag_default()
                self._rag = rag
            except Exception:
                rag = None
        if rag is not None and hasattr(rag, "observe"):
            try:
                rag.observe(
                    {
                        "id": item.get("id"),
                        "kind": item.get("kind"),
                        "name": item.get("name"),
                        "summary": item.get("summary"),
                        "confidence": item.get("confidence"),
                        "salience": item.get("salience"),
                        "expiry": item.get("expiry"),
                        "supersedes": item.get("supersedes"),
                        "tags": item.get("tags", []),
                        "details": item.get("properties", {}),
                    },
                    source=source,
                )
            except Exception:
                pass
        sdb = self._social_db
        if sdb is not None and hasattr(sdb, "world_memory"):
            try:
                sdb.world_memory.upsert(
                    memory_id=str(item.get("id") or ""),
                    kind=str(item.get("kind") or "observations"),
                    name=str(item.get("name") or ""),
                    summary=str(item.get("summary") or ""),
                    details=dict(item.get("properties") or {}),
                    source=source,
                    confidence=float(item.get("confidence", 0.5)),
                    salience=float(item.get("salience", 0.5)),
                    tags=list(item.get("tags") or []),
                    expiry=float(item.get("expiry", 0.0)),
                )
            except Exception:
                pass

    def schema(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": bool(self.cfg.get("enabled", True)),
            "kinds": list(SCHEMA.keys()),
            "schema": SCHEMA,
            "fields": [
                "id", "kind", "name", "summary", "properties", "source",
                "confidence", "salience", "count", "first_seen_ts", "last_seen_ts", "expiry", "supersedes", "tags",
            ],
            "persistence": self._persistence_status(),
        }

    def status(self, *, limit: Optional[int] = None, now: Optional[float] = None) -> Dict[str, Any]:
        ts_now = float(now if now is not None else time.time())
        with self._lock:
            self._purge_expired_unlocked(ts_now)
            counts = {kind: len(bucket) for kind, bucket in self._store.items()}
            recent_limit = _as_int(limit, _as_int(self.cfg.get("recent_limit"), 20))
            return {
                "ok": True,
                "enabled": bool(self.cfg.get("enabled", True)),
                "total": sum(counts.values()),
                "counts": counts,
                "kinds": list(SCHEMA.keys()),
                "recent": self.recent(limit=recent_limit, now=ts_now).get("items", []),
                "persistence": self._persistence_status(),
            }

    def observe(self, payload: Optional[Dict[str, Any]], *, source: str = "api", now: Optional[float] = None) -> Dict[str, Any]:
        if not bool(self.cfg.get("enabled", True)):
            return {"ok": False, "available": False, "reason": "world_memory_disabled"}
        data = _as_dict(payload)
        ts = float(now if now is not None else time.time())
        kind = _normalize_kind(data.get("kind") or data.get("type") or data.get("category"))
        name = _clean_text(data.get("name") or data.get("label") or data.get("title") or data.get("summary") or kind)
        summary = _clean_text(data.get("summary") or data.get("description") or name)
        src = _clean_text(data.get("source") or source or "api")
        observed_at = _as_float(data.get("observed_at"), ts)
        explicit_expiry = _as_float(data.get("expiry") or data.get("expiry_ts"), 0.0)
        ttl_s = _as_float(data.get("expiry_s") or self.cfg.get("default_expiry_s"), 0.0)
        expiry = explicit_expiry if explicit_expiry > observed_at else (observed_at + ttl_s if ttl_s > 0.0 else 0.0)
        supersedes = _clean_text(data.get("supersedes"))
        confidence = max(0.0, min(1.0, _as_float(data.get("confidence"), 0.6)))
        salience = max(0.0, min(1.0, _as_float(data.get("salience"), confidence)))
        properties = dict(_as_dict(data.get("properties")))
        for key in ("location", "transcript", "reason", "emotion", "object", "person"):
            if key in data and key not in properties:
                properties[key] = data.get(key)
        tags_raw = data.get("tags")
        if isinstance(tags_raw, list):
            tags = [_clean_text(x).lower() for x in tags_raw if _clean_text(x)]
        elif tags_raw:
            tags = [_clean_text(tags_raw).lower()]
        else:
            tags = []

        with self._lock:
            self._purge_expired_unlocked(ts)
            if supersedes:
                self._retire_superseded_unlocked(supersedes)
            key = self._key_for(kind, name, summary, src)
            bucket = self._store.setdefault(kind, {})
            created = key not in bucket
            if created:
                item = {
                    "id": f"{kind}:{key}",
                    "kind": kind,
                    "name": name,
                    "summary": summary,
                    "properties": properties,
                    "source": src,
                    "confidence": round(confidence, 3),
                    "salience": round(salience, 3),
                    "count": 1,
                    "first_seen_ts": ts,
                    "last_seen_ts": ts,
                    "observed_at": observed_at,
                    "expiry": expiry,
                    "supersedes": supersedes,
                    "tags": sorted(set(tags)),
                }
            else:
                item = dict(bucket[key])
                merged_props = dict(_as_dict(item.get("properties")))
                merged_props.update(properties)
                item["properties"] = merged_props
                item["summary"] = summary or item.get("summary", "")
                item["confidence"] = round(max(_as_float(item.get("confidence"), 0.0), confidence), 3)
                item["salience"] = round(max(_as_float(item.get("salience"), 0.0), salience), 3)
                item["count"] = _as_int(item.get("count"), 1) + 1
                item["last_seen_ts"] = ts
                item["observed_at"] = observed_at
                item["expiry"] = expiry
                if supersedes:
                    item["supersedes"] = supersedes
                item["tags"] = sorted(set(list(item.get("tags") or []) + tags))
            bucket[key] = item
            self._trim_kind(kind)
            history_item = {
                "timestamp": ts,
                "id": item.get("id"),
                "kind": kind,
                "name": name,
                "source": src,
                "created": created,
                "summary": summary,
            }
            self._history.append(history_item)
            self._history = self._history[-100:]
            self._dirty = True
            self._maybe_save_unlocked()
            item_copy = dict(item)
        self._sync_to_backing(item_copy, source=src)
        return {"ok": True, "available": True, "created": created, "item": item_copy, "timestamp": ts}

    def recent(self, *, kind: Optional[str] = None, limit: int = 10, now: Optional[float] = None) -> Dict[str, Any]:
        limit = max(1, min(100, _as_int(limit, 10)))
        ts_now = float(now if now is not None else time.time())
        kinds = [_normalize_kind(kind)] if kind else list(SCHEMA.keys())
        with self._lock:
            self._purge_expired_unlocked(ts_now)
            items: List[Dict[str, Any]] = []
            for k in kinds:
                bucket = self._store.get(k, {})
                for x in bucket.values():
                    if not self._is_expired(x, ts_now):
                        items.append(dict(x))
        items.sort(key=lambda x: _as_float(x.get("last_seen_ts"), 0.0), reverse=True)
        return {"ok": True, "kind": _normalize_kind(kind) if kind else "all", "limit": limit, "items": items[:limit], "count": len(items[:limit])}

    def get(self, item_id: str, *, now: Optional[float] = None) -> Dict[str, Any]:
        item_id = _clean_text(item_id)
        ts_now = float(now if now is not None else time.time())
        with self._lock:
            self._purge_expired_unlocked(ts_now)
            if ":" in item_id:
                kind, key = item_id.split(":", 1)
                kind = _normalize_kind(kind)
                item = self._store.get(kind, {}).get(key)
                if item and not self._is_expired(item, ts_now):
                    return {"ok": True, "available": True, "item": dict(item)}
            for bucket in self._store.values():
                for item in bucket.values():
                    if item.get("id") == item_id and not self._is_expired(item, ts_now):
                        return {"ok": True, "available": True, "item": dict(item)}
        return {"ok": True, "available": False, "reason": "not_found", "id": item_id}

    def clear(self, *, kind: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if kind:
                normalized = _normalize_kind(kind)
                removed = len(self._store.get(normalized, {}))
                self._store[normalized] = {}
                self._history.append({"timestamp": time.time(), "kind": normalized, "event": "clear", "removed": removed})
                self._dirty = True
                self._save()
                return {"ok": True, "kind": normalized, "removed": removed}
            removed = sum(len(bucket) for bucket in self._store.values())
            self._store = {k: {} for k in SCHEMA}
            self._history.append({"timestamp": time.time(), "kind": "all", "event": "clear", "removed": removed})
            self._dirty = True
            self._save()
            return {"ok": True, "kind": "all", "removed": removed}

    def history(self, *, limit: int = 20) -> Dict[str, Any]:
        limit = max(1, min(100, _as_int(limit, 20)))
        with self._lock:
            return {"ok": True, "items": list(self._history[-limit:]), "count": min(limit, len(self._history))}

    def flush(self) -> None:
        """Persist pending dirty changes to disk immediately."""
        with self._lock:
            if self._dirty:
                self._save()

    def _key_for(self, kind: str, name: str, summary: str, source: str) -> str:
        if kind in {"events"}:
            return _slug(f"{name}_{source}")
        if kind in {"observations"}:
            return _slug(f"{summary}_{source}")
        return _slug(name)

    def _trim_kind(self, kind: str) -> None:
        max_entries = max(10, _as_int(self.cfg.get("max_entries_per_kind"), 200))
        bucket = self._store.get(kind, {})
        if len(bucket) <= max_entries:
            return
        ordered = sorted(bucket.items(), key=lambda kv: (_as_float(kv[1].get("salience"), 0.0), _as_float(kv[1].get("last_seen_ts"), 0.0)))
        for key, _ in ordered[: max(0, len(bucket) - max_entries)]:
            bucket.pop(key, None)

    def _storage_file(self) -> Path:
        raw = _clean_text(self.cfg.get("storage_path"), ".sentrybot_state/world_memory.json")
        return resolve_repo_path(raw)

    def _persistence_enabled(self) -> bool:
        return bool(self.cfg.get("persistence_enabled", True))

    def _persistence_status(self) -> Dict[str, Any]:
        path = self._storage_file()
        return {
            "enabled": self._persistence_enabled(),
            "path": str(path),
            "exists": path.exists(),
            "loaded": self._loaded_from_disk,
            "error": self._last_persist_error,
        }

    def _load(self) -> None:
        if not self._persistence_enabled():
            return
        path = self._storage_file()
        try:
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            raw_store = data.get("store") if isinstance(data, dict) else None
            if isinstance(raw_store, dict):
                loaded: Dict[str, Dict[str, Dict[str, Any]]] = {kind: {} for kind in SCHEMA}
                for kind in SCHEMA:
                    bucket = raw_store.get(kind)
                    if isinstance(bucket, dict):
                        loaded[kind] = {str(key): dict(value) for key, value in bucket.items() if isinstance(value, dict)}
                self._store = loaded
            raw_history = data.get("history") if isinstance(data, dict) else None
            if isinstance(raw_history, list):
                self._history = [dict(x) for x in raw_history[-100:] if isinstance(x, dict)]
            self._loaded_from_disk = True
            self._last_persist_error = ""
            self._purge_expired_unlocked(time.time())
        except Exception as exc:
            self._last_persist_error = str(exc)

    def _maybe_save_unlocked(self) -> None:
        if not self._persistence_enabled() or not self._dirty:
            return
        interval = max(0.0, _as_float(self.cfg.get("save_interval_s"), 0.0))
        if interval <= 0.0 or (time.monotonic() - self._last_save_ts) >= interval:
            self._save()

    def _save(self) -> None:
        if not self._persistence_enabled():
            return
        path = self._storage_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "saved_at": time.time(),
                "store": self._store,
                "history": self._history[-100:],
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(path)
            self._dirty = False
            self._last_save_ts = time.monotonic()
            self._last_persist_error = ""
        except Exception as exc:
            self._last_persist_error = str(exc)
