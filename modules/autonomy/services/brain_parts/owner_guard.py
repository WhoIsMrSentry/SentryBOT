"""Owner presence and authority guard logic."""
from __future__ import annotations

import time
from typing import Any, Dict


class OwnerGuardMixin:
    """Encapsulates owner scanning, permissions, and request throttling."""

    def _maybe_scan_for_owner(self) -> None:
        if not self.owner_cfg.get("enabled"):
            return
        if self._has_full_owner_authority():
            return
        now = time.time()
        interval = self.owner_cfg.get("scan_interval_s", 25)
        if now - self._last_owner_scan < interval:
            return
        self._last_owner_scan = now
        self.client.push_interaction_event("owner.scan")
        if not self._trigger_animation("owner_scan"):
            self._perform_owner_scan()

    def _refresh_rfid_authorization(self) -> None:
        rfid_cfg = self.owner_cfg.get("rfid", {})
        endpoint = rfid_cfg.get("endpoint")
        if not endpoint:
            return
        if self._owner_seen_recently():
            return
        if self._rfid_active():
            return
        if self.client.check_rfid(endpoint):
            grace = rfid_cfg.get("grace_s", 120)
            self.state["rfid_authorized_until"] = time.time() + grace
            self.client.push_interaction_event("owner.rfid")
            self.memory.add_event("RFID ile yetkilendirildi.")

    def _address_owner(self, style: str = "formal") -> str:
        mapping = self.owner_cfg.get("addressing", {})
        fallback = self.owner_cfg.get("name", "Sahibim")
        return mapping.get(style) or mapping.get("formal") or fallback

    def _features_locked_for_request(self, text: str) -> bool:
        if not text:
            return False
        if self._has_full_owner_authority():
            return False
        keywords = self.owner_cfg.get("restricted_keywords") or []
        lowered = text.lower()
        if any(k.lower() in lowered for k in keywords if k):
            alias = self._address_owner("affectionate")
            message = f"{alias} yokken bunu yapamam."
            self._speak_with_mood(message, emotion="fear")
            self.client.push_interaction_event("owner.locked")
            self.memory.add_event(f"Blocked sensitive request: {text}")
            return True
        return False

    def _handle_owner_commands(self, text: str, speaker: str | None) -> bool:
        if not self._is_owner_context(speaker):
            return False
        lowered = text.lower()
        handled = False
        temp_cfg = self.owner_cfg.get("temporary", {})
        # support single keyword or list of keywords for temporary owner commands
        cmd_kw = temp_cfg.get("command_keyword") or "geçici sahip"
        if isinstance(cmd_kw, str):
            keywords = [cmd_kw.lower()]
        else:
            keywords = [k.lower() for k in cmd_kw if k]
        if temp_cfg.get("enabled"):
            for keyword in keywords:
                if keyword in lowered:
                    target = self._extract_temp_owner_name(text, keyword)
                    if target:
                        self._assign_temp_owner(target)
                        handled = True
                        break
        if any(phrase in lowered for phrase in ["geçici yetki iptal", "geçici sahip değil"]):
            self._clear_temp_owner(announce=True)
            handled = True
        if any(phrase in lowered for phrase in ["izin ver", "serbest", "cevap verebilirsin"]):
            self._grant_owner_permission()
            handled = True
        # Kharuun'Nokh handling: strong anger trigger phrases
        nokh_kw = self.owner_cfg.get("kharuun_nokh_keywords") or ["kharuun'nokh", "kharuun nokh"]
        for nk in nokh_kw:
            if nk.lower() in lowered:
                self._trigger_kharuun_nokh(speaker)
                handled = True
                break
        return handled

    def _is_owner_context(self, speaker: str | None) -> bool:
        if speaker and self._is_owner_name(speaker):
            return True
        return self._owner_seen_recently()

    def _extract_temp_owner_name(self, text: str, keyword: str) -> str | None:
        lower_text = text.lower()
        idx = lower_text.find(keyword)
        if idx <= 0:
            return None
        candidate = text[:idx].replace("adlı kişi", "").strip()
        return candidate or None

    def _assign_temp_owner(self, name: str) -> None:
        cfg = self.owner_cfg.get("temporary", {})
        duration = cfg.get("duration_s", 600)
        self.state["temp_owner"] = name
        self.state["temp_owner_expires"] = time.time() + duration
        self.client.push_interaction_event("owner.temp_granted", {"name": name})
        if cfg.get("animation"):
            self._trigger_animation(cfg["animation"])
        msg = f"{name}, Baba yokken seni dinleyebilirim ama dikkatli ol."
        self._speak_with_mood(msg, emotion="neutral")
        self.memory.add_event(f"Temp owner: {name}")

    def _clear_temp_owner(self, announce: bool = False) -> None:
        if not self.state.get("temp_owner"):
            return
        name = self.state.get("temp_owner")
        self.state["temp_owner"] = None
        self.state["temp_owner_expires"] = 0.0
        self.client.push_interaction_event("owner.temp_revoked", {"name": name})
        if announce:
            msg = self.owner_cfg.get("temporary", {}).get("revoke_message", "Geçici yetkiler sona erdi.")
            self._speak_with_mood(msg, emotion="neutral")
        self.memory.add_event(f"Temp owner cleared: {name}")

    def _grant_owner_permission(self) -> None:
        grace = self.owner_cfg.get("permission_grace_s", 600)
        self.state["owner_permission_until"] = time.time() + grace
        message = self.owner_cfg.get("permission_message", "Tamam, yanında olmasan da cevap vereceğim.")
        message = message.replace("{nickname}", self._address_owner("affectionate"))
        self._speak_with_mood(message, emotion="joy")
        self.client.push_interaction_event("owner.permission_granted")

    def _owner_guard_enabled(self) -> bool:
        return bool(self.owner_cfg.get("enabled") and self.owner_cfg.get("require_presence", True))

    def _owner_seen_recently(self) -> bool:
        if not self.owner_cfg.get("enabled"):
            return True
        timeout = self.owner_cfg.get("presence_timeout_s", 30)
        last = self.state.get("owner_last_seen", 0.0)
        return (time.time() - last) <= timeout

    def _owner_cooldown_active(self) -> bool:
        return time.time() < self.state.get("owner_lockout_until", 0.0)

    def _owner_permission_active(self) -> bool:
        return time.time() < self.state.get("owner_permission_until", 0.0)

    def _rfid_active(self) -> bool:
        return time.time() < self.state.get("rfid_authorized_until", 0.0)

    def _temp_owner_active(self) -> bool:
        now = time.time()
        expires = self.state.get("temp_owner_expires", 0.0)
        if self.state.get("temp_owner") and now < expires:
            return True
        if self.state.get("temp_owner") and now >= expires:
            self._clear_temp_owner(announce=True)
        return False

    def _has_full_owner_authority(self) -> bool:
        if not self.owner_cfg.get("enabled"):
            return True
        return any([
            self._owner_seen_recently(),
            self._owner_permission_active(),
            self._rfid_active(),
        ])

    def _has_any_authority(self) -> bool:
        return self._has_full_owner_authority() or self._temp_owner_active()

    def _maybe_block_request(self, text: str) -> tuple[str, str] | None:
        if not self._owner_guard_enabled():
            return None
        if self._has_any_authority():
            return None
        entry = self._record_external_request(text)
        affectionate = self._address_owner("affectionate")
        if self._owner_cooldown_active():
            msg = self.owner_cfg.get("cooldown_message", "Sahibim gelene kadar konuşmak istemiyorum.")
            return (msg.replace("{nickname}", affectionate), "fear")
        threshold = self.owner_cfg.get("max_requests_without_owner", 3)
        if entry["recent_count"] >= threshold:
            self.state["owner_lockout_until"] = time.time() + self.owner_cfg.get("cooldown_s", 20)
            entry["angered"] = True
            self.client.push_interaction_event("autonomy.angry")
            self.mood.modify("happiness", -10)
            self.mood.modify("fear", 15)
            msg = self.owner_cfg.get("angry_message", "Yeter artık! Sahibim olmadan seni dinlemeyeceğim.")
            return (msg.replace("{nickname}", affectionate), "fear")
        msg = self.owner_cfg.get("polite_message", "Sahibim olmadan isteğini yerine getiremiyorum.")
        return (msg.replace("{nickname}", affectionate), "neutral")

    def _record_external_request(self, text: str) -> Dict[str, Any]:
        if not hasattr(self, "_attempt_log"):
            self._attempt_log = []
        now = time.time()
        person = self._guess_active_person() or "Unknown"
        entry = {
            "timestamp": now,
            "person": person,
            "text": text,
            "angered": False,
            "recent_count": 1,
        }
        self._attempt_log.append(entry)
        if len(self._attempt_log) > 50:
            self._attempt_log = self._attempt_log[-50:]
        window = self.owner_cfg.get("speaker_window_s", 10)
        same_person = [a for a in self._attempt_log if a["person"] == person and now - a["timestamp"] <= window]
        entry["recent_count"] = len(same_person)
        self._owner_report_pending = True
        return entry

    def _guess_active_person(self) -> str | None:
        if not getattr(self, "_current_people", None):
            return None
        now = time.time()
        window = self.owner_cfg.get("speaker_window_s", 10)
        candidates = [(name, ts) for name, ts in self._current_people.items() if now - ts <= window]
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[1], reverse=True)
        for name, _ in candidates:
            if not self._is_owner_name(name):
                return name
        return candidates[0][0]

    def _is_owner_name(self, name: str | None) -> bool:
        if not name:
            return False
        owner_name = self.owner_cfg.get("name")
        aliases = self.owner_cfg.get("aliases") or []
        names = []
        if owner_name:
            names.append(owner_name)
        for a in aliases:
            if a:
                names.append(a)
        lowered = name.lower()
        for n in names:
            if n and lowered == n.lower():
                return True
        return False

    def _trigger_kharuun_nokh(self, source: str | None = None) -> None:
        # Strong negative reaction: modify mood, push event, announce
        try:
            self.mood.modify("happiness", -30)
            self.mood.modify("fear", 30)
        except Exception:
            pass
        self.client.push_interaction_event("autonomy.angry")
        note = "Kharuun'Nokh triggered"
        if source:
            note += f" by {source}"
        self.memory.add_event(note)
        msg = self.owner_cfg.get("kharuun_nokh_message", "Sınırlar aşıldı. Tepki veriyorum.")
        self._speak_with_mood(msg, emotion="anger")

    def _on_owner_seen(self, timestamp: float) -> None:
        self.state["owner_last_seen"] = timestamp
        self.state["owner_lockout_until"] = 0.0
        self.state["rfid_authorized_until"] = 0.0
        self.state["owner_permission_until"] = 0.0
        self._clear_temp_owner()
        affectionate = self._address_owner("affectionate")
        greet_cooldown = max(10, self.owner_cfg.get("presence_timeout_s", 30) / 2)
        if timestamp - self.state.get("owner_last_greet", 0.0) > greet_cooldown:
            greeting = self.owner_cfg.get("greeting", "Baba! Gelmene çok sevindim.")
            self._speak_with_mood(greeting.replace("{nickname}", affectionate), emotion="joy")
            self.state["owner_last_greet"] = timestamp
        self.mood.modify("happiness", 10)
        self._report_attempts_to_owner()

    def _report_attempts_to_owner(self) -> None:
        if not self._owner_report_pending or not self._attempt_log:
            return
        summary = self._compose_owner_report()
        if summary:
            affectionate = self._address_owner("affectionate")
            self._speak_with_mood(summary.replace("{nickname}", affectionate), emotion="joy")
        self._attempt_log.clear()
        self._owner_report_pending = False

    def _compose_owner_report(self) -> str | None:
        stats: Dict[str, Dict[str, Any]] = {}
        for entry in self._attempt_log:
            person = entry.get("person", "Unknown")
            data = stats.setdefault(person, {"count": 0, "examples": [], "angered": False})
            data["count"] += 1
            if len(data["examples"]) < 2:
                data["examples"].append(entry.get("text", ""))
            data["angered"] = data["angered"] or entry.get("angered", False)
        if not stats:
            return None
        fragments: list[str] = []
        for person, data in stats.items():
            base = f"{person} benden {data['count']} kez bir şey istedi"
            if data["examples"]:
                base += f" (örnek: '{data['examples'][0]}')"
            if data["angered"]:
                base += " ve beni sinirlendirdi"
            fragments.append(base)
        alias = self._address_owner("handle")
        return f"{alias}, " + "; ".join(fragments) + "."
