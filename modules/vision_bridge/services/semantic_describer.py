from __future__ import annotations
"""Scene semantic description and personalization layer.

Bu katman robotu daha "canlı" hissettirmek için algılanan objeleri,
kişileri ve tehlikeleri doğal dile çevirir. Ollama varsa kullanır;
yoksa kurallı basit bir özet üretir.
"""

import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("vision_bridge.semantic")

try:
    import httpx  # type: ignore
except Exception:
    httpx = None  # Fallback

class SemanticDescriber:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.last_llm_call = 0.0
        self.llm_interval_s = 5.0

    def build_prompt(self, objects: List[Dict[str, Any]]) -> str:
        parts = []
        for o in objects:
            lbl = o.get("label") or o.get("name") or "unknown"
            dist = o.get("distance_m")
            name = o.get("name")
            if name and name != "Unknown":
                lbl = name
            if dist:
                parts.append(f"{lbl} ~{dist}m")
            else:
                parts.append(lbl)
        scene_line = ". ".join(parts)
        return (
            "Sen bir arkadaş canlısı robot sensörüsün. Çevredeki varlıkları kısa, sıcak ve empatik Türkçe ile özetle. "
            f"Algılanan: {scene_line}. Duygusal ama abartısız konuş."
        )

    def llm_summarize(self, objects: List[Dict[str, Any]]) -> Optional[str]:
        if httpx is None:
            return None
        now = time.time()
        if now - self.last_llm_call < self.llm_interval_s:
            return None
        self.last_llm_call = now
        prompt = self.build_prompt(objects)
        url = self.config.get("ollama", {}).get("endpoint", "http://localhost:11434/api/generate")
        model = self.config.get("ollama", {}).get("model", "llama3")
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.post(url, json={"model": model, "prompt": prompt, "stream": False})
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response")
        except Exception as e:
            logger.debug(f"LLM summarize error: {e}")
        return None

    def fallback_summary(self, objects: List[Dict[str, Any]]) -> str:
        counts = {}
        for o in objects:
            lbl = o.get("label") or o.get("name") or "unknown"
            counts[lbl] = counts.get(lbl, 0) + 1
        parts = [f"{c} {n}" for n, c in counts.items()]
        return "Etrafımda " + ", ".join(parts) + " görüyorum." if parts else "Etrafta belirgin bir şey yok."

    def personalize(self, text: str, objects: List[Dict[str, Any]]) -> str:
        p_cfg = self.config.get("vision", {}).get("personalization", {})
        known_people = p_cfg.get("known_people", {})
        greetings = []
        for o in objects:
            name = o.get("name")
            if name and name in known_people:
                g = known_people[name].get("greeting")
                if g:
                    greetings.append(g)
        if greetings:
            text = " ".join(greetings) + " " + text
        return text

    def describe(self, objects: List[Dict[str, Any]]) -> str:
        llm_text = self.llm_summarize(objects)
        if not llm_text:
            llm_text = self.fallback_summary(objects)
        return self.personalize(llm_text, objects)
