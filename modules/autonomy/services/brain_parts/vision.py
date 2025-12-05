"""Vision sensing and reactions for AutonomyBrain."""
from __future__ import annotations

import random
import time
from typing import Any, Dict


class VisionMixin:
    """Handles periodic vision polling and reactions."""

    def _sense_vision(self) -> None:
        if not self._vision_cfg.get("enabled", False):
            return
        now = time.time()
        interval = self._vision_cfg.get("poll_interval_s", 3)
        last_poll = self.state.get("last_vision_poll", 0.0)
        if now - last_poll < interval:
            return
        self.state["last_vision_poll"] = now
        max_results = self._vision_cfg.get("max_results", 5)
        results = self.client.get_latest_vision_results(limit=max_results)
        if not results:
            return
        ignored = {label.lower() for label in self._vision_cfg.get("ignore_labels", [])}
        for res in results:
            label = (res.get("label") or "").lower()
            if label in ignored:
                continue
            self._handle_vision_result(res)
        decay_window = max(10, self.owner_cfg.get("speaker_window_s", 10))
        self._current_people = {
            name: ts for name, ts in self._current_people.items() if now - ts <= decay_window
        }

    def _handle_vision_result(self, result: Dict[str, Any]) -> None:
        name = result.get("name") or result.get("label")
        if not name:
            return
        now = time.time()
        self._current_people[name] = now
        cooldown = self._vision_cfg.get("person_cooldown_s", 25)
        last_seen = self._people_last_seen.get(name, 0.0)
        if now - last_seen < cooldown:
            return
        self._people_last_seen[name] = now
        self.state["last_interaction"] = now
        self.memory.add_event(f"Vision {name} tespit etti.")
        if name != "Unknown":
            self._track_person_stat(name)
        happiness_boost = 10 if name != "Unknown" else 4
        self.mood.modify("happiness", happiness_boost)
        self.mood.modify("curiosity", 5)
        self.client.push_interaction_event("vision.person", {"name": name})
        self._focus_on_target(result)
        should_speak = name != "Unknown" or self._vision_cfg.get("speak_on_unknown", False)
        if should_speak:
            utterance = self._compose_greeting_for_person(name, result)
            if utterance:
                emotion = "joy" if name != "Unknown" else "curiosity"
                self._speak_with_mood(utterance, emotion=emotion)
                self.memory.add_event(f"{name} ile konuştum: {utterance}")
        if self._is_owner_name(name):
            self._on_owner_seen(now)

    def _compose_greeting_for_person(self, name: str, result: Dict[str, Any]) -> str | None:
        if self._is_owner_name(name):
            return None
        summary = None
        try:
            record = self.client.get_person_memory(name)
            if record:
                summary = ((record.get("record") or {}).get("last_summary") or {}).get("text")
        except Exception:  # pragma: no cover - best effort enrichment
            summary = None
        distance = result.get("distance_m")
        prefer_llm = self._vision_cfg.get("prefer_llm_greetings", False)
        if prefer_llm and self.config.get("llm", {}).get("enabled", False):
            prompt = (
                "SentryBOT olarak kısa ve sıcak bir selamlama üret.\n"
                f"İsim: {name}\n"
                f"Mesafe: {distance if distance else 'bilinmiyor'}\n"
                f"Özet: {summary or 'özel bilgi yok'}\n"
                f"Mutluluk: {int(self.mood['happiness'])}/100, Enerji: {int(self.mood['energy'])}/100.\n"
                "10 kelimeyi geçme, Türkçe konuş."
            )
            try:
                resp = self.client.chat(prompt)
                if resp and resp.get("answer"):
                    return resp["answer"].strip()
            except Exception:
                pass
        pieces = [f"Merhaba {name}"]
        if distance:
            try:
                pieces.append(f"yaklaşık {float(distance):.1f} metre uzaklıktasın.")
            except Exception:
                pass
        if summary:
            pieces.append(summary[:120])
        return " ".join(pieces)

    def _focus_on_target(self, result: Dict[str, Any]) -> None:
        if self._trigger_animation("vision_focus"):
            return
        self.client.push_interaction_event("vision.focus", {"label": result.get("label")})
        jitter = random.randint(-5, 5)
        target = max(0, min(180, self.state["current_pan"] + jitter))
        self.client.move_head(target, self.state["current_tilt"])
        self._blink_fallback()
