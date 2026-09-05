from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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
        res = self.memory.search_memory(query, limit=5)
        if not res:
            return "No matching memories found."
        return str(res)

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
