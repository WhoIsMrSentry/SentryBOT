from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("autonomy.world_memory")


class WorldMemoryMixin:
    """Mixin for world memory queries, observations, autowriting, and memory bias."""

    def observe_context_world_memory(self, source_type: str, context: Optional[dict] = None) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            if not hasattr(self, "world_memory_autowriter"):
                return {"ok": False, "available": False, "reason": "world_memory_autowriter_missing"}
            payloads = self.world_memory_autowriter.build(source_type, context or {})
            results = []
            for payload in payloads:
                src = payload.get("source") if isinstance(payload, dict) else source_type
                results.append(self.world_memory.observe(payload, source=src or source_type))
            snapshot = {
                "ok": True,
                "available": True,
                "source_type": source_type,
                "count": len(results),
                "items": [r.get("item", {}) for r in results if isinstance(r, dict)],
                "created_count": sum(1 for r in results if isinstance(r, dict) and r.get("created")),
            }
            self.state["world_memory"] = self.world_memory.status()
            self.state["world_memory_autowrite"] = snapshot
            history = list(self.state.get("world_memory_autowrite_history") or [])
            history.append({
                "source_type": source_type,
                "count": snapshot.get("count", 0),
                "created_count": snapshot.get("created_count", 0),
                "items": [
                    {"id": item.get("id"), "kind": item.get("kind"), "name": item.get("name")}
                    for item in snapshot.get("items", [])
                    if isinstance(item, dict)
                ],
            })
            self.state["world_memory_autowrite_history"] = history[-50:]
            return snapshot
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc), "source_type": source_type}

    def get_world_memory_autowrite_snapshot(self) -> dict:
        try:
            current = self.state.get("world_memory_autowrite")
            if isinstance(current, dict) and current:
                data = dict(current)
            else:
                data = {"ok": True, "available": False, "reason": "never_written", "count": 0, "items": []}
            data["history"] = list(self.state.get("world_memory_autowrite_history") or [])[-10:]
            return data
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_memory_needs_bias_snapshot(self) -> dict:
        try:
            if hasattr(self, "memory_needs_bias"):
                return self.memory_needs_bias.snapshot()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
        return {"ok": False, "available": False, "reason": "memory_needs_bias_missing"}

    def evaluate_memory_needs_bias(self, payload: Optional[dict] = None) -> dict:
        try:
            if not hasattr(self, "memory_needs_bias"):
                return {"ok": False, "available": False, "reason": "memory_needs_bias_missing"}
            data = payload if isinstance(payload, dict) else {}
            needs = data.get("needs") if isinstance(data.get("needs"), dict) else data.get("needs_snapshot")
            shadow = data.get("shadow") if isinstance(data.get("shadow"), dict) else data.get("memory_shadow")
            return self.memory_needs_bias.apply(
                needs if isinstance(needs, dict) else {},
                shadow if isinstance(shadow, dict) else {},
                now=data.get("now"),
            )
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_memory_decision_shadow(self) -> dict:
        try:
            if not hasattr(self, "world_memory") or not hasattr(self, "memory_decision_shadow"):
                return {"ok": False, "available": False, "reason": "memory_decision_shadow_missing"}
            snapshot = self.world_memory.status()
            recent_result = self.world_memory.recent(limit=25)
            recent = recent_result.get("items", []) if isinstance(recent_result, dict) else []
            result = self.memory_decision_shadow.evaluate(snapshot, recent)
            self.state["memory_decision_shadow"] = result
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def evaluate_memory_decision_shadow(self, payload: Optional[dict] = None) -> dict:
        try:
            if not hasattr(self, "memory_decision_shadow"):
                return {"ok": False, "available": False, "reason": "memory_decision_shadow_missing"}
            data = payload if isinstance(payload, dict) else {}
            snapshot = data.get("memory") if isinstance(data.get("memory"), dict) else data
            recent = data.get("recent") if isinstance(data.get("recent"), list) else None
            return self.memory_decision_shadow.evaluate(snapshot, recent, now=data.get("now"))
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_world_memory_snapshot(self) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            result = self.world_memory.status()
            self.state["world_memory"] = result
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_world_memory_schema(self) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            return self.world_memory.schema()
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def observe_world_memory(self, payload: Optional[dict] = None, source: str = "api") -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            result = self.world_memory.observe(payload or {}, source=source)
            self.state["world_memory"] = self.world_memory.status()
            history = list(self.state.get("world_memory_history") or [])
            item = result.get("item") if isinstance(result, dict) else {}
            history.append({
                "timestamp": result.get("timestamp") if isinstance(result, dict) else None,
                "id": item.get("id") if isinstance(item, dict) else "",
                "kind": item.get("kind") if isinstance(item, dict) else "",
                "name": item.get("name") if isinstance(item, dict) else "",
                "created": result.get("created") if isinstance(result, dict) else False,
                "source": item.get("source") if isinstance(item, dict) else source,
            })
            self.state["world_memory_history"] = history[-50:]
            try:
                self.client.push_interaction_event(
                    "memory.observe",
                    {
                        "kind": item.get("kind") if isinstance(item, dict) else "",
                        "name": item.get("name") if isinstance(item, dict) else "",
                        "created": result.get("created") if isinstance(result, dict) else False,
                    },
                )
            except Exception:
                pass
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_world_memory_recent(self, kind: Optional[str] = None, limit: int = 10) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            return self.world_memory.recent(kind=kind or None, limit=limit)
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def recall_world_memory(self, query: str = "", limit: int = 8) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            if hasattr(self.world_memory, "recall"):
                return self.world_memory.recall(query or "", limit=limit)
            return self.world_memory.recent(limit=limit)
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def get_world_memory_context(self, query: str = "", limit: int = 8) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing", "context": ""}
            if hasattr(self.world_memory, "build_context"):
                return self.world_memory.build_context(query or "", limit=limit)
            recent = self.world_memory.recent(limit=limit)
            items = recent.get("items", []) if isinstance(recent, dict) else []
            lines = [
                f"- {i.get('kind')}:{i.get('name')} | {i.get('summary')}"
                for i in items
                if isinstance(i, dict)
            ]
            return {"ok": True, "available": True, "query": query or "", "context": "\n".join(lines), "items": items}
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc), "context": ""}

    def get_world_memory_history(self, limit: int = 20) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            return self.world_memory.history(limit=limit)
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}

    def clear_world_memory(self, kind: Optional[str] = None) -> dict:
        try:
            if not hasattr(self, "world_memory"):
                return {"ok": False, "available": False, "reason": "world_memory_missing"}
            result = self.world_memory.clear(kind=kind or None)
            self.state["world_memory"] = self.world_memory.status()
            return result
        except Exception as exc:
            return {"ok": False, "available": False, "error": str(exc)}
