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
        now = time.time()
        poll_interval_s = float(rfid_cfg.get("poll_interval_s", 5.0))
        last_check = float(self.state.get("rfid_last_check", 0.0) or 0.0)
        if poll_interval_s > 0 and (now - last_check) < poll_interval_s:
            return
        self.state["rfid_last_check"] = now
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
        # Delegation is intentionally disabled: owner cannot transfer authority
        # to a third person via voice commands.
        return False

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

    def _rfid_active(self) -> bool:
        return time.time() < self.state.get("rfid_authorized_until", 0.0)

    def _has_full_owner_authority(self) -> bool:
        if not self.owner_cfg.get("enabled"):
            return True
        return any([
            self._owner_seen_recently(),
            self._rfid_active(),
        ])

    def _maybe_block_request(self, text: str) -> tuple[str, str] | None:
        if not self._owner_guard_enabled():
            return None
        if self._has_full_owner_authority():
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

    # Kharuun irreversible trigger removed to simplify owner rules.

    def _on_owner_seen(self, timestamp: float) -> None:
        self.state["owner_last_seen"] = timestamp
        self.state["owner_lockout_until"] = 0.0
        self.state["rfid_authorized_until"] = 0.0
        affectionate = self._address_owner("affectionate")
        greet_cooldown = max(10, self.owner_cfg.get("presence_timeout_s", 30) / 2)
        if timestamp - self.state.get("owner_last_greet", 0.0) > greet_cooldown:
            greeting = self.owner_cfg.get("greeting", "Baba! Gelmene çok sevindim.")
            ran = self._run_scene(
                "owner_return",
                context={"name": self.owner_cfg.get("name", "Owner"), "nickname": affectionate},
            )
            if not ran:
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
