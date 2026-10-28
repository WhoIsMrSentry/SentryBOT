from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    pass

logger = logging.getLogger("agent.tools.social")


class SocialToolsMixin:
    """Social and Interaction tools for ToolRegistry."""

    def speak(self, text: str, tone: str = "", language: str = "") -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return "Error: nothing to speak."
        payload: Dict[str, Any] = {"text": cleaned}
        if tone:
            payload["tone"] = str(tone).strip().lower()
        if language:
            payload["language"] = str(language).strip().lower()
        result = self.queue_action("speak", priority=60, ttl_ms=10000, payload=payload)
        if result.startswith("Action queued"):
            return f"Speaking: {cleaned[:80]}"
        return result

    def oled_face(self, expression: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        key = str(expression or "").strip().lower()
        pip_activities = {
            "listening",
            "thinking",
            "scanning",
            "searching",
            "working",
            "processing",
            "connecting",
            "sleep",
            "alert",
        }
        legacy_anims = {"scan", "emotive", "blink", "wink", "all", "icons"}
        if key in pip_activities or key in legacy_anims:
            resp = self.client.oled_anim(key)
        else:
            resp = self.client.oled_show(key)
        return f"OLED face updated to {expression}. Response: {resp}"

    def set_emotion(self, emotion: str) -> str:
        """Compatibility wrapper: route emotion changes through Expression service."""
        return self.express_emotion(
            emotion=emotion,
            intensity=1.0,
            duration_s=3.0,
            modalities=["leds", "oled", "head"],
            text=None,
            language="tr",
        )

    def express_emotion(
        self,
        emotion: str,
        intensity: float = 1.0,
        duration_s: float = 3.0,
        modalities: list[str] | None = None,
        text: str | None = None,
        language: str = "tr",
    ) -> str:
        """Express an emotion across all modalities through the Expression service."""
        if not self.client:
            return "Error: Hardware client disconnected."
        try:
            int(min(2.0, max(0.1, float(intensity))))
            dur = min(30.0, max(0.5, float(duration_s)))
            mods = list(modalities) if modalities else ["leds", "oled", "voice", "head"]
            try:
                from modules.common.emotion_vocab import get_vocab

                render = get_vocab().get_render_dict(emotion)
                canon = render["canonical"]
            except Exception:
                render = None
                canon = str(emotion).strip().lower()
            try:
                resp = self._http.post(
                    "/expression/express",
                    json_data={
                        "emotion": canon,
                        "intensity": round(float(intensity), 3),
                        "duration_s": round(float(dur), 3),
                        "modalities": mods,
                        "text": text,
                        "language": str(language or "tr"),
                    },
                    timeout=3.0,
                )
                if resp.status_code == 200:
                    body = resp.json()
                    ok = body.get("ok", False)
                    if not ok:
                        return f"Expression skipped: {body.get('reason', 'unknown')}"
                    return (
                        f"Expressed {canon} (intensity={intensity:.2f}, "
                        f"{duration_s:.1f}s) across {', '.join(mods)}. "
                        f"Render: LED={render['neopixel']['effect']} "
                        f"RGB={render['neopixel']['rgb'] if render else 'n/a'}, "
                        f"OLED={render['oled']['animation'] if render else 'n/a'}, "
                        f"TTS={render['voice']['tone'] if render else 'n/a'}"
                    )
                return f"Expression failed: HTTP {resp.status_code}"
            except Exception as exc:
                return f"Expression failed: {exc}"
        except (TypeError, ValueError) as exc:
            return f"Expression parameter error: {exc}"

    def interaction_event(self, event: str) -> str:
        if not self.client:
            return "Error: Hardware client disconnected."
        self.client.push_interaction_event(event)
        return f"Triggered complex interaction event: {event}"

    def search_memory(self, query: str) -> str:
        q = str(query or "").strip()
        if not q:
            return "No matching memories found."
        results: List[str] = []

        # 1. Episodic memory
        if getattr(self, "memory", None) is not None and hasattr(self.memory, "search_memory"):
            try:
                episodic = self.memory.search_memory(q, limit=5) or []
                for item in episodic:
                    if isinstance(item, dict):
                        results.append(f"[episodic:{item.get('type', 'log')}] {item.get('content', '')}")
                    else:
                        results.append(str(item))
            except Exception:
                pass

        # 2. WorldMemoryRAG (structured facts, objects, places, people, habits)
        try:
            from modules.cognitive_memory.services.world_memory_rag import WorldMemoryRAG

            wm = WorldMemoryRAG()
            wm_res = wm.recall(q, limit=4)
            for item in (wm_res.get("items") or []) if isinstance(wm_res, dict) else []:
                if float(item.get("rank_score", 0.0)) >= 0.20:
                    results.append(f"[world:{item.get('kind', 'fact')}:{item.get('name', '')}] {item.get('summary', '')}")
        except Exception:
            pass

        # 3. ChatRAG (semantic long-term dialogue chunks with ONNX E5 rerank)
        try:
            from modules.cognitive_memory.services.chat_rag import get_default as _get_chat_rag

            rag = _get_chat_rag()
            for item in rag.recall(q, limit=4):
                if float(item.get("score", 0.0)) >= 0.25:
                    results.append(f"[chat_rag:{item.get('role', 'chat')}] {item.get('text', '')}")
        except Exception:
            pass

        if not results:
            return "No matching memories found."
        return "\n".join(results[:10])

    def remember_fact(self, fact: str, category: str = "observation", subject: str = "") -> str:
        """Save a durable fact, preference, or object location into long-term & semantic RAG memory."""
        cleaned_fact = str(fact or "").strip()
        if not cleaned_fact:
            return "Error: empty fact."
        cat = str(category or "observation").strip().lower() or "observation"
        subj = str(subject or cleaned_fact[:32]).strip() or cat
        saved_to: List[str] = []

        if getattr(self, "memory", None) is not None and hasattr(self.memory, "remember"):
            try:
                self.memory.remember("fact", f"[{cat}:{subj}] {cleaned_fact}", importance=8)
                saved_to.append("episodic")
            except Exception:
                pass

        try:
            from modules.cognitive_memory.services.world_memory_rag import WorldMemoryRAG

            wm = WorldMemoryRAG()
            res = wm.observe(
                {
                    "kind": cat,
                    "name": subj,
                    "summary": cleaned_fact,
                    "confidence": 0.90,
                    "salience": 0.85,
                },
                source="agent_tool",
            )
            if isinstance(res, dict) and res.get("ok"):
                saved_to.append("world_memory_rag")
        except Exception:
            pass

        try:
            from modules.cognitive_memory.services.chat_rag import get_default as _get_chat_rag

            rag = _get_chat_rag()
            if rag.ingest(person_id=subj, role="fact", text=cleaned_fact, kind=cat):
                saved_to.append("chat_rag")
        except Exception:
            pass

        if not saved_to:
            return "Error: could not persist fact."
        return f"Remembered ({', '.join(saved_to)}): [{cat}:{subj}] {cleaned_fact}"

    def search_social_memory(self, name: str, query: str = "") -> str:
        try:
            from modules.cognitive_memory import get_default as _social_default

            db = _social_default()
        except Exception:
            return "Social memory unavailable."
        if db is None:
            return "Social memory unavailable."
        rec = db.persons.get_by_name(str(name or "").strip())
        if not rec:
            return f"No social record for {name}."
        pid = rec["id"]
        grouped = db.relationships.list_grouped(pid)
        moments = db.moments.top_for_person(pid, limit=10)
        snippets = [
            str(m.get("text", "")).strip()
            for m in moments
            if str(m.get("text", "")).strip()
        ]
        q = str(query or "").strip()
        if q and snippets:
            try:
                from modules.agent_core.services.semantic_index import rank

                ranked = rank(q, snippets, top_k=3)
                snippets = [snippets[idx] for idx, _ in ranked if idx < len(snippets)]
            except Exception:
                pass
        parts: List[str] = []
        trust = float(rec.get("trust_score", 0.0) or 0.0)
        parts.append(f"trust_score={trust:.2f}")
        for key in ("likes", "dislikes", "topics"):
            vals = (
                grouped.get(key, []) if isinstance(grouped.get(key, []), list) else []
            )
            if vals:
                parts.append(f"{key}: {', '.join(str(v) for v in vals[:6])}")
        if snippets:
            parts.append("moments: " + " | ".join(snippets[:3]))
        return "\n".join(parts) if parts else "No social memories found."
