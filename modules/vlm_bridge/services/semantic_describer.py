from __future__ import annotations
"""Scene semantic description and personalization layer.

Bu katman robotu daha "canlı" hissettirmek için algılanan objeleri,
kişileri ve tehlikeleri doğal dile çevirir. Ollama varsa kullanır;
yoksa kurallı basit bir özet üretir.
"""

import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("vlm_bridge.semantic")

try:
    from .llm_client import generate_text
except Exception:
    from modules.vlm_bridge.services.llm_client import generate_text  # type: ignore

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
            "Sen bir arkadaş canlısı robot sensörüsün. Türkçe cevap ver. "
            "Sahneyi 2-3 cümlede anlat: önce genel durum, sonra önemli kişi/nesneler ve mümkünse mesafe bilgisi. "
            "Sıcak ve empatik ol ama tek cümleye düşme. "
            f"Algılanan: {scene_line}."
        )

    def llm_summarize(self, objects: List[Dict[str, Any]]) -> Optional[str]:
        now = time.time()
        if now - self.last_llm_call < self.llm_interval_s:
            return None
        self.last_llm_call = now
        prompt = self.build_prompt(objects)
        llm_cfg = self.config.get("ollama", {}) if isinstance(self.config.get("ollama", {}), dict) else {}
        timeout = float(llm_cfg.get("timeout", 5.0))
        return generate_text(prompt, llm_cfg, timeout=timeout, response_lang="tr")

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
