from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
import requests

try:
    from .vision_event_bus import (
        EVENT_HAZARD_DETECTED,
        EVENT_NEW_PERSON,
        EVENT_OWNER_SEEN,
    )
except Exception:
    EVENT_HAZARD_DETECTED = "hazard_detected"
    EVENT_NEW_PERSON = "new_person"
    EVENT_OWNER_SEEN = "owner_seen"

try:
    from .llm_client import generate_text
except Exception:
    from modules.vlm_bridge.services.llm_client import generate_text  # type: ignore

logger = logging.getLogger("vlm_bridge.identity_events")


class ProcessorIdentityEventsMixin:
    """Blind mode speech, proximity hazards, person greetings, and LLM followups."""

    config: Dict[str, Any]
    semantic: Any
    memory: Any
    event_bus: Optional[Any]
    last_blind_announcement: float
    last_alert_announcement: float
    _last_person_greet: Dict[str, float]
    person_identity: Optional[Any]
    _gateway_base: str
    mode_flags: Dict[str, bool]

    def _handle_blind_mode(self, results: List[Dict[str, Any]]) -> None:
        now = time.time()
        interval = float(self.config.get("vision", {}).get("blind_mode", {}).get("interval_seconds", 5.0))
        if now - self.last_blind_announcement < interval:
            return
        if not results:
            return

        text = self.semantic.describe(results)
        for r in results:
            name = r.get("name")
            if name and name != "Unknown":
                self.memory.set_summary(name, text)

        self._send_tts(text)
        self.last_blind_announcement = now

    def _send_tts(self, text: str) -> None:
        out_text = str(text or "")
        tcfg = self.config.get("translation", {}) if isinstance(self.config.get("translation", {}), dict) else {}
        if out_text and bool(tcfg.get("enabled", False)):
            endpoint = str(tcfg.get("endpoint", "http://localhost:8080/ollama/translate"))
            source_lang = str(tcfg.get("source_lang", "auto"))
            target_lang = str(tcfg.get("target_lang", "tr"))
            timeout = float(tcfg.get("timeout", 1.5))
            try:
                resp = requests.post(
                    endpoint,
                    params={"text": out_text, "source_lang": source_lang, "target_lang": target_lang},
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("ok") and data.get("text"):
                        out_text = str(data.get("text"))
            except Exception as exc:
                logger.debug("vlm_bridge translation failed: %s", exc)

        url = self.config.get("speak", {}).get("endpoint") or "http://127.0.0.1:8080/speak/say"
        try:
            requests.post(url, json={"text": out_text}, timeout=1.0)
        except Exception as exc:
            logger.debug("Failed to send TTS: %s", exc)

    def _evaluate_alerts(self, results: List[Dict[str, Any]]) -> None:
        vision_cfg = self.config.get("vision", {})
        alerts_cfg = vision_cfg.get("alerts", {})
        if not alerts_cfg or not self.mode_flags.get("hazards", True):
            return

        classes = {str(c) for c in alerts_cfg.get("classes", []) if str(c).lower() not in {"person", "human", "face"}}
        if not classes:
            return
        dist_thr = float(alerts_cfg.get("distance_threshold_m", 1.0))
        announce_interval = float(alerts_cfg.get("announce_interval_s", 10.0))
        now = time.time()
        if now - self.last_alert_announcement < announce_interval:
            return

        hazards = []
        for r in results:
            lbl = str(r.get("label") or "")
            dist = r.get("distance_m")
            if lbl in classes and isinstance(dist, (int, float)) and float(dist) <= dist_thr:
                hazards.append((lbl, float(dist)))
        if not hazards:
            return

        parts = [f"{lbl} {dist:.1f}m" for lbl, dist in hazards]
        self._send_tts("Dikkat yakın tehlike: " + ", ".join(parts))
        self._emit_emotion("alert")
        if self.event_bus is not None:
            self.event_bus.publish(EVENT_HAZARD_DETECTED, {"hazards": parts})
        self.last_alert_announcement = now

    def _emit_emotion(self, emotion: str) -> None:
        try:
            from modules.gateway.url import gateway_url

            requests.post(
                gateway_url(self._gateway_base, "/interactions/event"),
                json={"type": f"autonomy.{emotion}"},
                timeout=0.5,
            )
        except Exception:
            pass

    def _handle_person_interactions(self, results: List[Dict[str, Any]]) -> None:
        vision_cfg = self.config.get("vision", {})
        if not self.mode_flags.get("people", True):
            return

        greet_cooldown = float(vision_cfg.get("personalization", {}).get("greet_cooldown_s", 30))
        now = time.time()
        for r in results:
            name = r.get("name")
            if not name or name == "Unknown":
                continue
            if self.person_identity is not None:
                rec = self.person_identity.recognize(
                    name=str(name),
                    confidence=float(r.get("confidence", 0.0) or 0.0),
                    face_score=float(r.get("confidence", 0.0) or 0.0),
                )
                r["person_id"] = rec.person_id
                r["recognition_level"] = rec.recognition_level
                r["relationship"] = rec.relationship
                if rec.recognition_level >= 5 and self.event_bus is not None:
                    self.event_bus.publish(EVENT_OWNER_SEEN, {"name": rec.name, "person_id": rec.person_id})
                elif rec.seen_count <= 2 and self.event_bus is not None:
                    self.event_bus.publish(EVENT_NEW_PERSON, {"name": rec.name, "person_id": rec.person_id})
            last = self._last_person_greet.get(name, 0.0)
            if now - last < greet_cooldown:
                continue

            greeting = self._build_greeting(name)
            if greeting:
                self._send_tts(greeting)
            self._emit_emotion("excited")
            self.memory.append_chat(name, role="system", text=f"Greeted: {greeting}")

            follow = self._ollama_followup(name)
            if follow:
                self._send_tts(follow)
                self.memory.append_chat(name, role="assistant", text=follow)

            self._last_person_greet[name] = now

    def _build_greeting(self, name: str) -> Optional[str]:
        p_cfg = self.config.get("vision", {}).get("personalization", {})
        known = p_cfg.get("known_people", {})
        if name in known:
            return known[name].get("greeting")
        return f"Merhaba {name}, seni gordugume sevindim."

    def _ollama_followup(self, name: str) -> Optional[str]:
        rec = self.memory.get_person(name) or {}
        last_sum = (rec.get("last_summary") or {}).get("text")
        prompt = (
            f"{name} ile karsilastin. {('Ozet: ' + last_sum) if last_sum else ''} "
            "Turkce sicak ve dogal bir karsilama yap. 2 cumle kur; "
            "ilk cumle samimi selamlama, ikinci cumle baglama uygun kisa bir takip sorusu olsun."
        )
        llm_cfg = self.config.get("ollama", {}) if isinstance(self.config.get("ollama", {}), dict) else {}
        timeout = float(llm_cfg.get("timeout", 4.0))
        return generate_text(prompt, llm_cfg, timeout=timeout, response_lang="tr")
